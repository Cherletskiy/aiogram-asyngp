import asyncio

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from db_init import database, init_db

import logging
from logging.handlers import RotatingFileHandler

import random
import configparser

from crud import add_user, add_base_cards, add_card, get_cards, delete_card_db, get_random_card, update_stats, get_user_stats


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler("app.log", maxBytes=1024*1024, backupCount=50, encoding="utf-8", delay=True),
        logging.StreamHandler()
    ]
)


# Чтение конфигурационного файла
config = configparser.ConfigParser()
config.read('settings.ini')
bot_token = config["tokens"]["bot_token"]

# Инициализация бота
dp = Dispatcher()
bot = Bot(token=bot_token)

# Основная клавиатура
base_keyboard = types.ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [types.KeyboardButton(text="📈 Статистика 📈")],
        [types.KeyboardButton(text="➕ Добавить карточку 📝"), types.KeyboardButton(text="❌ Удалить карточку 📝")],
        [types.KeyboardButton(text="📚 Запустить тест (случайные карточки) 📚")]
    ]
)

# Клавиатура отмены
cancel_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ Отменить", callback_data='cancel')]
    ])


@dp.message(Command("start"))
async def start_command(message: types.Message) -> None:
    """Обрабатывает команду /start, регистрирует пользователя и отображает главное меню.
    Происходит запрос к БД для добавления пользователя с помощью функции add_user из crud.py."""
    await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await message.answer(f'Привет, {message.from_user.full_name} 👋\n\nРад тебя видеть 😊\n\nВыбери действие из меню.', reply_markup=base_keyboard)

    logging.info(f"User {message.from_user.id} started the bot")


class TestState(StatesGroup):
    """Состояния тестирования пользователя."""
    waiting_for_answer = State()


@dp.message(F.text == "⏭ Пропустить")
async def skip_card(message: types.Message, state: FSMContext):
    """Функция для пропуска текущей карточки.
    Запускает следующую карточку и добавляет количество пропущенных ответов."""
    data = await state.get_data()
    skipped_answers = data.get("skipped_answers", 0) + 1
    await state.update_data(skipped_answers=skipped_answers)

    await send_card(message, state)
    logging.info(f"User {message.from_user.id} skipped a card")


@dp.message(F.text == "🔚 Завершить")
async def end_test(message: types.Message, state: FSMContext):
    """Функция для завершения тестирования.
    Отправляет результаты тестирования и очищает состояние."""
    data = await state.get_data()

    correct_answers = data.get("correct_answers", 0)
    incorrect_answers = data.get("incorrect_answers", 0)
    skipped_answers = data.get("skipped_answers", 0)

    total_questions = correct_answers + incorrect_answers
    accuracy = round((correct_answers / total_questions) * 100, 2) if total_questions > 0 else 0

    result_message = (
        f"📊 *Результаты теста:*\n\n"
        f"✅ Правильных ответов: *{correct_answers}*\n"
        f"❌ Неправильных ответов: *{incorrect_answers}*\n"
        f"⏭ Пропущено: *{skipped_answers}*\n"
        f"🎯 Точность (без учета пропусков): *{accuracy}%*\n"
    )

    await message.answer(result_message, reply_markup=base_keyboard)
    await state.clear()

    logging.info(f"User {message.from_user.id} finished the test")


@dp.message(F.text == "📚 Запустить тест (случайные карточки) 📚")
async def send_card(message: types.Message, state: FSMContext) -> None:
    """Запускает тест и отправляет пользователю случайную карточку.
    Из функции get_random_card из crud.py в data возвращается target_card.id, target_card.translate, target_card.target_word, answer_words (случайные слова)."""
    user_id = message.from_user.id

    data = await get_random_card(user_id)

    if not data:
        await message.answer("❌ Нет доступных карточек для тестирования.")
        await state.clear()
        return

    card_id, translate, target_word, words = data
    words.append(target_word)
    random.shuffle(words)

    await state.update_data(
        card_id=card_id,
        translate=translate,
        target_word=target_word,
        words=words
    )

    await message.answer(
        f"Выбери корректный перевод слова: \n'{translate}'",
        reply_markup=types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=[
                [types.KeyboardButton(text=word) for word in words[:2]],
                [types.KeyboardButton(text=word) for word in words[2:]],
                [types.KeyboardButton(text="⏭ Пропустить"), types.KeyboardButton(text="🔚 Завершить")]
            ]
        )
    )

    await state.set_state(TestState.waiting_for_answer)

    logging.info(f"User {message.from_user.id} started the test")


@dp.message(TestState.waiting_for_answer)
async def check_answer(message: types.Message, state: FSMContext):
    """Функция для проверки ответа пользователя.
    Проверяет ответ пользователя и обновляет статистику с помощью update_stats из crud.py.
    Обновляет состояние тестирования и отправляет следующую карточку."""
    user_answer = message.text
    user_id = message.from_user.id

    data = await state.get_data()
    target_word = data["target_word"]

    if "correct_answers" not in data:
        await state.update_data(correct_answers=0, incorrect_answers=0, skipped_answers=0)
        data = await state.get_data()

    correct_answers = data["correct_answers"]
    incorrect_answers = data["incorrect_answers"]

    if user_answer == target_word:
        response_list = ["✅ Правильно!", "✅ Молодец!", "✅ Так держать!", "✅ Всё верно!"]
        response = random.choice(response_list)
        correct_answers += 1
        await update_stats(user_id, correct=True)
    else:
        response_list = ["❌ Неправильно!", "❌ Ошибка!", "❌ Близко, но неверно!", "❌ Неверно!"]
        response = f"{random.choice(response_list)} \n\nВерный ответ: \n'{target_word}'"
        incorrect_answers += 1
        await update_stats(user_id, correct=False)

    await message.answer(response, reply_markup=types.ReplyKeyboardRemove())
    await state.update_data(correct_answers=correct_answers, incorrect_answers=incorrect_answers)

    await asyncio.sleep(0.05)
    await send_card(message, state)

    logging.info(f"User {message.from_user.id} answered the question correctly {user_answer}, target word: {target_word}" if user_answer == target_word
                 else f"User {message.from_user.id} answered the question incorrectly {user_answer}, target word: {target_word}")


class AddCard(StatesGroup):
    """Cостояние для добавления карточек."""
    waiting_info = State()


CARD_FIELDS = ["translate", "target_word"]


@dp.message(F.text == "➕ Добавить карточку 📝")
async def add_card_start(message: types.Message, state: FSMContext):
    """Начинает процесс добавления карточки"""
    await state.set_state(AddCard.waiting_info)
    await state.update_data(step=0, card_data={})

    await message.answer("Введите слово на русском:", reply_markup=cancel_keyboard)

    logging.info(f"User {message.from_user.id} started adding a card")


@dp.message(AddCard.waiting_info)
async def process_card_step(message: types.Message, state: FSMContext):
    """ Процесс добавления карточки.
    Пользователь вводит слово на русском и перевод. Карточка сохраняется в БД с помощью add_card из crud.py."""
    data = await state.get_data()
    step = data.get("step", 0)
    card_data = data.get("card_data", {})

    field_name = CARD_FIELDS[step]
    card_data[field_name] = message.text

    step += 1

    if step < len(CARD_FIELDS):
        await state.update_data(step=step, card_data=card_data)
        prompts = ["Введите слово на русском:", "Введите перевод:"]
        await message.answer(prompts[step], reply_markup=cancel_keyboard)
    else:
        await add_card(message.from_user.id, card_data["translate"], card_data["target_word"])
        await state.clear()
        await message.answer(f"✅ Карточка '{card_data['translate']}' добавлена!", reply_markup=base_keyboard)

        logging.info(f"User {message.from_user.id} added a card {card_data['translate']}")


class DeleteState(StatesGroup):
    """Состояние для удаления карточек."""
    waiting_for_card_id = State()


@dp.message(F.text == "❌ Удалить карточку 📝")
async def delete_card(message: types.Message, state: FSMContext):
    """ Функция для удаления карточки. Пользователю выводится список карточек с помощью get_cards из crud.py.
    Затем происходит запрос на ввод ID карточки для удаления."""
    await state.set_state(DeleteState.waiting_for_card_id)

    cards = await get_cards(message.from_user.id)

    if not cards:
        await message.answer("❌ У вас нет карточек для удаления.", reply_markup=base_keyboard)
        await state.clear()

        logging.warning(f"User {message.from_user.id} tried to delete a card, but they had no cards to delete.")
        return

    await state.update_data(id=[card.id for card in cards])

    cards_string = "ID - Слово\n" + "\n".join([f"{card.id} - {card.translate}" for card in cards])
    await message.answer(f"{cards_string}\n\nУкажите ID карточки для удаления: ", reply_markup=cancel_keyboard)


@dp.message(DeleteState.waiting_for_card_id)
async def delete_card_process(message: types.Message, state: FSMContext):
    """ Функция для удаления карточки по ID.
    После получения ID функция проверяет его на корректность и удаляет карточку из БД с помощью delete_card_db из crud.py."""
    data = await state.get_data()
    card_id = message.text

    if not await check_value(card_id, data["id"]):
        await asyncio.sleep(0.5)
        await message.answer("❌ Указан некорректный ID. Попробуй ещё.", reply_markup=cancel_keyboard)

        logging.warning(f"User {message.from_user.id} entered an incorrect card ID for deletion.")
    else:
        await delete_card_db(int(card_id))
        await state.clear()
        await message.answer("✅ Карточка удалена.", reply_markup=base_keyboard)

        logging.info(f"User {message.from_user.id} deleted a card with ID {card_id}")


async def check_value(value: str, lst: list):
    """ Функция для проверки значения. Вызывается в функции delete_card_id.
    ID должен быть числом и быть в списке lst (карточек пользователя)."""
    if not value.isdigit():
        return False
    if int(value) not in lst:
        return False
    return True


@dp.callback_query(F.data == "cancel")
async def cancel(query: types.CallbackQuery, state: FSMContext):
    """ Функция для отмены текущего процесса."""
    current_state = await state.get_state()

    if current_state is None:
        await query.answer("❌ Нет активного процесса для отмены!", show_alert=True)
        logging.warning(f"User {query.from_user.id} tried to cancel a non-existent process.")
        return

    await state.clear()

    await query.message.edit_reply_markup(reply_markup=None)

    await query.answer("Действие отменено")
    await query.message.answer("❌ Действие отменено.", reply_markup=base_keyboard)

    logging.info(f"User {query.from_user.id} canceled a process {current_state}")


@dp.message(F.text == "📈 Статистика 📈")
async def get_stat(message: types.Message):
    """Функция для получения статистики пользователя.
    Статистика содержит количество правильных и неправильных ответов. Их число возвращает get_user_stats из crud.py."""
    user_id = message.from_user.id

    stats = await get_user_stats(user_id)

    if stats[0] and stats[1]:
        correct = stats[0]
        incorrect = stats[1]
        total = correct + incorrect

        accuracy = round((correct / total) * 100, 2) if total > 0 else 0

        result_message = (
            f"📊 *Статистика за все время:*\n\n"
            f"✅ Правильных ответов: *{correct}*\n"
            f"❌ Неправильных ответов: *{incorrect}*\n"
            f"🎯 Точность: *{accuracy}%*\n"
        )

        await message.answer(result_message, reply_markup=base_keyboard)

        logging.info(f"User {user_id} got statistics: {result_message}")
    else:
        await message.answer("❌ Пока нет данных для статистики.", reply_markup=base_keyboard)

        logging.warning(f"No statistics found for user {user_id}")


@dp.message()
async def command(message: types.Message):
    """ Функция для обработки неизвестных команд."""
    await message.answer("❌ Неизвестная команда. \nВоспользутесь меню.", reply_markup=base_keyboard)

    logging.warning(f"User {message.from_user.id} entered an unknown command: {message.text}")


async def main():
    await database.connect()
    await init_db()
    await add_base_cards()
    try:
        await dp.start_polling(bot)
    finally:
        await database.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

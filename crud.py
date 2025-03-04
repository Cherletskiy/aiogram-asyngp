from db_init import AsyncSessionLocal
from models import User, Card, UserCard, UserStats

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from sqlalchemy import or_

import random


async def get_session() -> AsyncSession:
    """Функция для получения сессии"""
    async with AsyncSessionLocal() as session:
        yield session


async def add_user(user_id: int, name: str, full_name: str):
    """Функция для добавления пользователя в модель User. Добавление происходит, если его ещё нет в БД."""
    async with AsyncSessionLocal() as session:
        check_user = await session.execute(select(User).filter(User.user_id == user_id))
        user = check_user.scalar()
        if not user:
            user = User(user_id=user_id, name=name, full_name=full_name)
            session.add(user)
            await session.commit()


async def get_random_card(user_id):
    """Функция для получения случайной карточки и вариантов ответов.
    Для получения случайной карточки должно быть минимум 4 карточки в БД общих и пользователя.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Card)
            .join(UserCard, isouter=True)
            .filter(or_(UserCard.user_id == None, UserCard.user_id == user_id))
            .order_by(func.random())
            .limit(4)
        )
        cards = result.scalars().all()

        if len(cards) < 4:
            return None

        target_card = random.choice(cards)
        cards.remove(target_card)

        random_answers = random.sample(cards, 3)

        answer_words = [word.target_word for word in random_answers]

        return target_card.id, target_card.translate, target_card.target_word, answer_words


async def add_card(user_id: int, translate: str, target_word: str):
    """Функция для добавления карточки в модель Card.
    Также добавляется связь между пользователем и карточкой в модели UserCard."""
    async with AsyncSessionLocal() as session:
        card = Card(translate=translate, target_word=target_word)
        session.add(card)
        await session.commit()

        user_card = UserCard(user_id=user_id, card_id=card.id)
        session.add(user_card)
        await session.commit()


async def get_cards(user_id: int):
    """Функция для получения всех карточек пользователя."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Card)
            .join(UserCard)
            .filter(UserCard.user_id == user_id))
        cards = result.scalars().all()
        return cards


async def delete_card_db(card_id: int):
    """Функция для удаления карточки из модели Card."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Card)
            .filter(Card.id == card_id))
        card = result.scalars().first()

        await session.delete(card)
        await session.commit()


async def update_stats(user_id: int, correct: bool):
    """Функция для обновления статистики пользователя.
    Происходит запрос на получение статистики пользователя.
    Если статистика есть, то обновляется количество правильных и неправильных ответов.
    Если статистики нет, то создается новая статистика с начальными значениями."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserStats)
            .filter(UserStats.user_id == user_id)
        )
        stats = result.scalars().first()

        if stats:
            if correct:
                stats.correct_answers += 1
            else:
                stats.incorrect_answers += 1
        else:
            stats = UserStats(
                user_id=user_id,
                correct_answers=1 if correct else 0,
                incorrect_answers=0 if correct else 1
            )
            session.add(stats)

        await session.commit()


async def get_user_stats(user_id: int):
    """Функция для получения статистики пользователя."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                func.sum(UserStats.correct_answers),
                func.sum(UserStats.incorrect_answers)
            )
            .filter(UserStats.user_id == user_id)
        )
        stats = result.fetchone()
        return stats


async def add_base_cards():
    """Функция для добавления базовых карточек в модель Card.
    Если базовых карточек нет в БД, то добавляются базовые карточки."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Card)
            .join(UserCard, isouter=True)
            .filter(UserCard.user_id == None)
        )
        cards = result.scalar()

        if not cards:

            cards = [
                Card(translate="Привет", target_word="Hello"),
                Card(translate="Я", target_word="I"),
                Card(translate="Ты", target_word="You"),
                Card(translate="Он", target_word="He"),
                Card(translate="Она", target_word="She"),
                Card(translate="Они", target_word="They"),
                Card(translate="Синий", target_word="Blue"),
                Card(translate="Красный", target_word="Red"),
                Card(translate="Машина", target_word="Car"),
                Card(translate="Дом", target_word="House")
            ]

            session.add_all(cards)

            await session.commit()




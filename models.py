from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    name = Column(String)
    full_name = Column(String)

    cards = relationship("UserCard", back_populates="user", cascade="all, delete-orphan")
    stats = relationship("UserStats", back_populates="user", cascade="all, delete-orphan")


class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    translate = Column(String)
    target_word = Column(String)

    users = relationship("UserCard", back_populates="card", cascade="all, delete-orphan")


class UserCard(Base):
    __tablename__ = "users_cards"

    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    card_id = Column(Integer, ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True)

    user = relationship("User", back_populates="cards")
    card = relationship("Card", back_populates="users")


class UserStats(Base):
    __tablename__ = "user_stats"

    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    correct_answers = Column(Integer, default=0)
    incorrect_answers = Column(Integer, default=0)

    user = relationship("User", back_populates="stats")

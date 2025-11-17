# app/models/dao.py

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ArtWork(Base):
    """
    Арт-работа конкурса.
    Таблица: art_works
    """
    __tablename__ = "art_works"

    id = Column(Integer, primary_key=True, index=True)
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # кто автор (можем не использовать, если автор не из Gappick)
    author = relationship("User", backref="art_works", lazy="joined", foreign_keys=[author_user_id])

    author_name = Column(String(255))              # произвольное имя автора (из формы)
    title = Column(String(255), nullable=False)    # название работы
    image_url = Column(Text, nullable=False)       # ссылка на картинку (CDN / Telegram / S3 и т.п.)
    description = Column(Text)                     # доп. описание
    round = Column(String(50))                     # например 'final', 'semi', 'group_a'
    short_code = Column(String(32), unique=True)   # удобный короткий код (A12, B07 и т.д.)
    status = Column(String(20), nullable=False, default="active")  # active / hidden / disqualified

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DaoProposal(Base):
    """
    Один "пропозал" (голосование DAO).
    Таблица: dao_proposals
    """
    __tablename__ = "dao_proposals"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(64), nullable=False, unique=True)  # 'art-final-2025'
    title = Column(String(255), nullable=False)
    description = Column(Text)
    type = Column(String(50), nullable=False, default="art_contest")  # на будущее под другие типы
    status = Column(String(20), nullable=False, default="draft")      # draft / open / closed

    snapshot_at = Column(DateTime(timezone=True), nullable=True)
    closes_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # связи
    options = relationship(
        "DaoOption",
        back_populates="proposal",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    votes = relationship(
        "DaoVote",
        back_populates="proposal",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DaoOption(Base):
    """
    Вариант голосования внутри одного пропозала.
    Для арт-конкурса каждая опция обычно привязана к ArtWork.
    Таблица: dao_options
    """
    __tablename__ = "dao_options"

    id = Column(Integer, primary_key=True, index=True)
    proposal_id = Column(Integer, ForeignKey("dao_proposals.id", ondelete="CASCADE"), nullable=False)
    art_work_id = Column(Integer, ForeignKey("art_works.id", ondelete="SET NULL"), nullable=True)

    # Можно хранить свой title, либо всегда брать из art_work.title
    title = Column(String(255), nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    proposal = relationship("DaoProposal", back_populates="options")
    art_work = relationship("ArtWork", lazy="joined")

    votes = relationship(
        "DaoVote",
        back_populates="option",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DaoVote(Base):
    """
    Голос пользователя.
    Один user может иметь по одной записи на опцию в рамках одного пропозала.
    Таблица: dao_votes
    """
    __tablename__ = "dao_votes"

    id = Column(BigInteger, primary_key=True, index=True)
    proposal_id = Column(Integer, ForeignKey("dao_proposals.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    option_id = Column(Integer, ForeignKey("dao_options.id", ondelete="CASCADE"), nullable=False)

    # Вес = количество $GAP, которое пользователь поставил за эту опцию
    weight = Column(BigInteger, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    proposal = relationship("DaoProposal", back_populates="votes")
    option = relationship("DaoOption", back_populates="votes")
    user = relationship("User", backref="dao_votes")

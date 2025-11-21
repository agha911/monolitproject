from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ArtWork(Base):
    """
    Арт-работа конкурса.
    Таблица: art_works

    Приведена к схеме, которую использует CRUD:
      - external_id
      - title
      - image_url
      - author_telegram_id
      - meta (JSON)
    """
    __tablename__ = "art_works"

    id = Column(Integer, primary_key=True, index=True)

    # внешний идентификатор (например, код группы/раунда и т.п.)
    external_id = Column(String(128), nullable=True, unique=True)

    title = Column(String(255), nullable=False)
    image_url = Column(Text, nullable=True)

    # автор из Telegram (если автор — пользователь Gappick)
    author_telegram_id = Column(BigInteger, nullable=True, index=True)

    # любое доп. описание/метаданные (раунд, статус, короткий код, и т.п.)
    meta = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DaoProposal(Base):
    """
    Один "пропозал" (голосование DAO).
    Таблица: dao_proposals

    Приведена к схеме, которую использует CRUD:
      - title, description
      - starts_at, ends_at
      - snapshot_at
      - is_active
    """
    __tablename__ = "dao_proposals"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    # Окно голосования
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)

    # На будущее, если захотим "снимать снапшот" баланса
    snapshot_at = Column(DateTime(timezone=True), nullable=True)

    # Используется в list_active_proposals / cast_vote
    is_active = Column(Boolean, nullable=False, default=True)

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

    Приведена к схеме, которую использует CRUD:
      - art_work_id
      - label (подпись, если нужна)
    """
    __tablename__ = "dao_options"

    id = Column(Integer, primary_key=True, index=True)

    proposal_id = Column(
        Integer,
        ForeignKey("dao_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )

    art_work_id = Column(
        Integer,
        ForeignKey("art_works.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Текстовая подпись варианта (можно не использовать, если всё из ArtWork)
    label = Column(String(255), nullable=True)

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

    proposal_id = Column(
        Integer,
        ForeignKey("dao_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    option_id = Column(
        Integer,
        ForeignKey("dao_options.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Вес = количество $GAP, которое пользователь поставил за эту опцию
    weight = Column(BigInteger, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    proposal = relationship("DaoProposal", back_populates="votes")
    option = relationship("DaoOption", back_populates="votes")
    user = relationship("User", backref="dao_votes")


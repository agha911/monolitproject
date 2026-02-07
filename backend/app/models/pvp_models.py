# backend/app/models/pvp_models.py
# PvP/Challenge + state tables (invites, matchmaking queue)

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

# ⚠️ Подстрой импорт Base под твою структуру проекта.
# Если у тебя Base лежит в другом месте — замени строку ниже.
from app.database.base import Base


class PvpMatch(Base):
    """
    PvP Live матч (2 игрока, ставка, клики, победитель или ничья).
    """
    __tablename__ = "pvp_matches"

    id = Column(Integer, primary_key=True)

    player1_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    player2_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    player1_clicks = Column(Integer, nullable=False)
    player2_clicks = Column(Integer, nullable=False)

    stake = Column(Integer, nullable=False, default=50000)

    # winner_id = NULL если ничья
    winner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    is_draw = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    player1 = relationship("User", foreign_keys=[player1_id], lazy="joined")
    player2 = relationship("User", foreign_keys=[player2_id], lazy="joined")
    winner = relationship("User", foreign_keys=[winner_id], lazy="joined")

    __table_args__ = (
        CheckConstraint("player1_clicks >= 0", name="ck_pvp_matches_player1_clicks_nonneg"),
        CheckConstraint("player2_clicks >= 0", name="ck_pvp_matches_player2_clicks_nonneg"),
        CheckConstraint("stake >= 0", name="ck_pvp_matches_stake_nonneg"),
        CheckConstraint("player1_id <> player2_id", name="ck_pvp_matches_players_not_equal"),
        # Если ничья — winner_id должен быть NULL
        CheckConstraint("(is_draw = false) OR (winner_id IS NULL)", name="ck_pvp_matches_draw_winner_null"),
        Index("ix_pvp_matches_players_pair_created", "player1_id", "player2_id", "created_at"),
    )


class ChallengeMatch(Base):
    """
    Challenge матч (асинхрон): игрок против best_result оппонента.
    Без ставок. Победа = +1 victory (логикой), лимит 5/день (логикой).
    """
    __tablename__ = "challenge_matches"

    id = Column(Integer, primary_key=True)

    challenger_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    challenger_clicks = Column(Integer, nullable=False)
    opponent_best_result = Column(Integer, nullable=False)

    is_win = Column(Boolean, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    challenger = relationship("User", foreign_keys=[challenger_id], lazy="joined")
    opponent = relationship("User", foreign_keys=[opponent_id], lazy="joined")

    __table_args__ = (
        CheckConstraint("challenger_clicks >= 0", name="ck_challenge_matches_challenger_clicks_nonneg"),
        CheckConstraint("opponent_best_result >= 0", name="ck_challenge_matches_opponent_best_result_nonneg"),
        CheckConstraint("challenger_id <> opponent_id", name="ck_challenge_matches_players_not_equal"),
        Index("ix_challenge_matches_pair_created", "challenger_id", "opponent_id", "created_at"),
    )


class PvpInvite(Base):
    """
    Инвайт на PvP-дуэль по ссылке.
    Жизненный цикл:
      created -> accepted | cancelled | expired
    """
    __tablename__ = "pvp_invites"

    id = Column(Integer, primary_key=True)

    code = Column(String(64), nullable=False, unique=True, index=True)

    creator_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    stake = Column(Integer, nullable=False, default=50000)

    # status: created | accepted | cancelled | expired
    status = Column(String(16), nullable=False, default="created", index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    creator = relationship("User", foreign_keys=[creator_user_id], lazy="joined")
    opponent = relationship("User", foreign_keys=[opponent_user_id], lazy="joined")

    __table_args__ = (
        CheckConstraint("stake >= 0", name="ck_pvp_invites_stake_nonneg"),
        CheckConstraint("creator_user_id <> opponent_user_id", name="ck_pvp_invites_users_not_equal"),
        CheckConstraint(
            "status IN ('created','accepted','cancelled','expired')",
            name="ck_pvp_invites_status_allowed",
        ),
        Index("ix_pvp_invites_creator_status_created", "creator_user_id", "status", "created_at"),
    )


class PvpQueue(Base):
    """
    Очередь матчмейкинга PvP Live без Redis.

    - user_id уникален (1 заявка на пользователя)
    - status: waiting | matched | left | expired
    - matched_user_id + match_token проставляются при подборе
    """
    __tablename__ = "pvp_queue"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    stake = Column(Integer, nullable=False, default=50000)

    # status: waiting | matched | left | expired
    status = Column(String(16), nullable=False, default="waiting", index=True)

    matched_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    match_token = Column(String(128), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), index=True)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    matched_user = relationship("User", foreign_keys=[matched_user_id], lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_pvp_queue_user_id"),
        CheckConstraint("stake >= 0", name="ck_pvp_queue_stake_nonneg"),
        CheckConstraint(
            "status IN ('waiting','matched','left','expired')",
            name="ck_pvp_queue_status_allowed",
        ),
        CheckConstraint(
            "(status <> 'matched') OR (matched_user_id IS NOT NULL AND match_token IS NOT NULL)",
            name="ck_pvp_queue_matched_requires_fields",
        ),
        CheckConstraint(
            "user_id <> matched_user_id",
            name="ck_pvp_queue_users_not_equal",
        ),
        Index("ix_pvp_queue_status_created_at", "status", "created_at"),
        Index("ix_pvp_queue_status_updated_at", "status", "updated_at"),
    )

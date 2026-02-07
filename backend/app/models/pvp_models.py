# backend/app/models/pvp_models.py
# Отдельный файл под PvP/Challenge таблицы

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Index,
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

    # Relationships (опционально, но удобно для админки/истории)
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
        # Если не ничья — winner_id может быть NULL только если ты это допускаешь (обычно нет)
        # Если хочешь строго: раскомментируй строку ниже
        # CheckConstraint("(is_draw = true) OR (winner_id IS NOT NULL)", name="ck_pvp_matches_not_draw_winner_not_null"),
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

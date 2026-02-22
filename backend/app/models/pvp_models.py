# backend/app/models/pvp_models.py
# PvP/Challenge + state tables (invites, matchmaking queue, sessions)

from __future__ import annotations

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
    text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class PvpMatch(Base):
    __tablename__ = "pvp_matches"

    id = Column(Integer, primary_key=True)

    player1_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    player2_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    player1_clicks = Column(Integer, nullable=False)
    player2_clicks = Column(Integer, nullable=False)

    stake = Column(Integer, nullable=False, default=50000)

    winner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    is_draw = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    # ⚠️ важно: НЕ joined, иначе SELECT с FOR UPDATE может тащить JOIN-ы
    player1 = relationship("User", foreign_keys=[player1_id], lazy="selectin")
    player2 = relationship("User", foreign_keys=[player2_id], lazy="selectin")
    winner = relationship("User", foreign_keys=[winner_id], lazy="selectin")

    __table_args__ = (
        CheckConstraint("player1_clicks >= 0", name="ck_pvp_matches_player1_clicks_nonneg"),
        CheckConstraint("player2_clicks >= 0", name="ck_pvp_matches_player2_clicks_nonneg"),
        CheckConstraint("stake >= 0", name="ck_pvp_matches_stake_nonneg"),
        CheckConstraint("player1_id <> player2_id", name="ck_pvp_matches_players_not_equal"),
        CheckConstraint("(is_draw = false) OR (winner_id IS NULL)", name="ck_pvp_matches_draw_winner_null"),
        Index("ix_pvp_matches_players_pair_created", "player1_id", "player2_id", "created_at"),
    )


class ChallengeMatch(Base):
    __tablename__ = "challenge_matches"

    id = Column(Integer, primary_key=True)

    challenger_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    challenger_clicks = Column(Integer, nullable=False)
    opponent_best_result = Column(Integer, nullable=False)

    is_win = Column(Boolean, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    challenger = relationship("User", foreign_keys=[challenger_id], lazy="selectin")
    opponent = relationship("User", foreign_keys=[opponent_id], lazy="selectin")

    __table_args__ = (
        CheckConstraint("challenger_clicks >= 0", name="ck_challenge_matches_challenger_clicks_nonneg"),
        CheckConstraint("opponent_best_result >= 0", name="ck_challenge_matches_opponent_best_result_nonneg"),
        CheckConstraint("challenger_id <> opponent_id", name="ck_challenge_matches_players_not_equal"),
        Index("ix_challenge_matches_pair_created", "challenger_id", "opponent_id", "created_at"),
    )


class PvpInvite(Base):
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

    creator = relationship("User", foreign_keys=[creator_user_id], lazy="selectin")
    opponent = relationship("User", foreign_keys=[opponent_user_id], lazy="selectin")

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
    __tablename__ = "pvp_queue"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    stake = Column(Integer, nullable=False, default=50000)

    # status: waiting | matched | left | expired
    status = Column(String(16), nullable=False, default="waiting", index=True)

    matched_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    match_token = Column(String(128), nullable=True, index=True)

    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), index=True)

    user = relationship("User", foreign_keys=[user_id], lazy="selectin")
    matched_user = relationship("User", foreign_keys=[matched_user_id], lazy="selectin")

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
        Index("ix_pvp_queue_status_expires_at", "status", "expires_at"),
    )


class PvpSession(Base):
    __tablename__ = "pvp_sessions"

    id = Column(Integer, primary_key=True)

    match_token = Column(String(128), nullable=False, unique=True, index=True)

    player1_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    player2_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    stake = Column(Integer, nullable=False, default=50000)

    mode = Column(String(16), nullable=True, index=True)

    invite_id = Column(Integer, ForeignKey("pvp_invites.id", ondelete="SET NULL"), nullable=True, index=True)

    # status: active | finished | expired | cancelled
    status = Column(String(16), nullable=False, default="active", index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    # ---- NEW: each player submits their own clicks ----
    player1_reported_clicks = Column(Integer, nullable=True)
    player2_reported_clicks = Column(Integer, nullable=True)
    player1_reported_at = Column(DateTime(timezone=True), nullable=True)
    player2_reported_at = Column(DateTime(timezone=True), nullable=True)

    # store created match id to serve status quickly
    match_id = Column(Integer, ForeignKey("pvp_matches.id", ondelete="SET NULL"), nullable=True, index=True)

    player1 = relationship("User", foreign_keys=[player1_id], lazy="selectin")
    player2 = relationship("User", foreign_keys=[player2_id], lazy="selectin")

    invite = relationship("PvpInvite", foreign_keys=[invite_id], lazy="selectin")
    match = relationship("PvpMatch", foreign_keys=[match_id], lazy="selectin")

    __table_args__ = (
        UniqueConstraint("match_token", name="uq_pvp_sessions_match_token"),
        CheckConstraint("stake >= 0", name="ck_pvp_sessions_stake_nonneg"),
        CheckConstraint("player1_id <> player2_id", name="ck_pvp_sessions_players_not_equal"),
        CheckConstraint(
            "status IN ('active','finished','expired','cancelled')",
            name="ck_pvp_sessions_status_allowed",
        ),
        CheckConstraint(
            "(mode IS NULL) OR (mode IN ('invite','matchmaking'))",
            name="ck_pvp_sessions_mode_allowed",
        ),
        Index("ix_pvp_sessions_status_created_at", "status", "created_at"),
        Index("ix_pvp_sessions_status_expires_at", "status", "expires_at"),
    )


class PvpChallengeAttempt(Base):
    __tablename__ = "pvp_challenge_attempts"

    id = Column(Integer, primary_key=True, index=True)

    challenger_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    opponent_best_result = Column(Integer, nullable=False)

    status = Column(String(16), nullable=False, server_default="started")  # started | finished | expired

    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, server_default=(func.now() + func.make_interval(0, 0, 0, 0, 0, 10, 0)))  # +10 minutes

    finished_at = Column(DateTime(timezone=True), nullable=True)
    challenger_clicks = Column(Integer, nullable=True)
    is_win = Column(Boolean, nullable=True)

    challenger = relationship("User", foreign_keys=[challenger_id])
    opponent = relationship("User", foreign_keys=[opponent_id])


class PvpWeeklySeason(Base):
    __tablename__ = "pvp_weekly_seasons"

    id = Column(Integer, primary_key=True)

    season_no = Column(Integer, nullable=False, unique=True, index=True)

    start_at = Column(DateTime(timezone=True), nullable=False, index=True)
    end_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # active | finished
    status = Column(String(16), nullable=False, server_default="active", index=True)

    finalized_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    __table_args__ = (
        CheckConstraint("status IN ('active','finished')", name="ck_pvp_weekly_seasons_status_allowed"),
        CheckConstraint("end_at > start_at", name="ck_pvp_weekly_seasons_range"),
    )


class PvpWeeklyLeaderboardRow(Base):
    __tablename__ = "pvp_weekly_leaderboard"

    id = Column(Integer, primary_key=True)

    season_id = Column(Integer, ForeignKey("pvp_weekly_seasons.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    rank = Column(Integer, nullable=False)
    victories = Column(Integer, nullable=False)
    best_result = Column(Integer, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    season = relationship("PvpWeeklySeason", lazy="selectin")
    user = relationship("User", lazy="selectin")

    __table_args__ = (
        CheckConstraint("rank >= 1", name="ck_pvp_weekly_lb_rank"),
        CheckConstraint("victories >= 0", name="ck_pvp_weekly_lb_victories"),
        CheckConstraint("best_result >= 0", name="ck_pvp_weekly_lb_best"),
        UniqueConstraint("season_id", "rank", name="uq_pvp_weekly_lb_season_rank"),
        UniqueConstraint("season_id", "user_id", name="uq_pvp_weekly_lb_season_user"),
    )

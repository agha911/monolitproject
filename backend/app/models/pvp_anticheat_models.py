from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class PvpLiveTelemetry(Base):
    __tablename__ = "pvp_live_telemetry"

    id = Column(Integer, primary_key=True)

    session_id = Column(Integer, ForeignKey("pvp_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    match_token = Column(String(128), nullable=False, index=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    player_slot = Column(String(16), nullable=False)  # player1 | player2

    reported_clicks = Column(Integer, nullable=False)
    validated_clicks = Column(Integer, nullable=False)

    client_started_at_ms = Column(Integer, nullable=True)
    client_finished_at_ms = Column(Integer, nullable=True)

    tap_count = Column(Integer, nullable=True)
    max_concurrent_touches = Column(Integer, nullable=True)

    avg_taps_per_sec = Column(Float, nullable=True)
    peak_taps_per_sec = Column(Float, nullable=True)

    send_batches_count = Column(Integer, nullable=True)

    had_pauses = Column(Boolean, nullable=True)
    pause_count = Column(Integer, nullable=True)
    longest_pause_ms = Column(Integer, nullable=True)

    suspicion_score = Column(Integer, nullable=False, default=0)
    confidence = Column(Float, nullable=True)
    is_suspicious = Column(Boolean, nullable=False, default=False)

    reason = Column(String(128), nullable=True)
    flags_json = Column(JSON, nullable=True)
    raw_payload_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    session = relationship("PvpSession", lazy="selectin")
    user = relationship("User", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_pvp_live_telemetry_session_user"),
        CheckConstraint("reported_clicks >= 0", name="ck_pvp_live_tel_reported_nonneg"),
        CheckConstraint("validated_clicks >= 0", name="ck_pvp_live_tel_validated_nonneg"),
        CheckConstraint("(tap_count IS NULL) OR (tap_count >= 0)", name="ck_pvp_live_tel_tap_count_nonneg"),
        CheckConstraint(
            "(max_concurrent_touches IS NULL) OR (max_concurrent_touches >= 0)",
            name="ck_pvp_live_tel_touches_nonneg",
        ),
        CheckConstraint(
            "(avg_taps_per_sec IS NULL) OR (avg_taps_per_sec >= 0)",
            name="ck_pvp_live_tel_avg_tps_nonneg",
        ),
        CheckConstraint(
            "(peak_taps_per_sec IS NULL) OR (peak_taps_per_sec >= 0)",
            name="ck_pvp_live_tel_peak_tps_nonneg",
        ),
        CheckConstraint(
            "(pause_count IS NULL) OR (pause_count >= 0)",
            name="ck_pvp_live_tel_pause_count_nonneg",
        ),
        CheckConstraint(
            "(longest_pause_ms IS NULL) OR (longest_pause_ms >= 0)",
            name="ck_pvp_live_tel_longest_pause_nonneg",
        ),
        CheckConstraint(
            "(player_slot IN ('player1','player2'))",
            name="ck_pvp_live_tel_player_slot_allowed",
        ),
        Index("ix_pvp_live_tel_session_created", "session_id", "created_at"),
        Index("ix_pvp_live_tel_user_created", "user_id", "created_at"),
        Index("ix_pvp_live_tel_suspicious", "is_suspicious", "created_at"),
    )


class PvpChallengeTelemetry(Base):
    __tablename__ = "pvp_challenge_telemetry"

    id = Column(Integer, primary_key=True)

    attempt_id = Column(Integer, ForeignKey("pvp_challenge_attempts.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    challenger_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    reported_clicks = Column(Integer, nullable=False)
    validated_clicks = Column(Integer, nullable=False)

    client_started_at_ms = Column(Integer, nullable=True)
    client_finished_at_ms = Column(Integer, nullable=True)

    tap_count = Column(Integer, nullable=True)
    max_concurrent_touches = Column(Integer, nullable=True)

    avg_taps_per_sec = Column(Float, nullable=True)
    peak_taps_per_sec = Column(Float, nullable=True)

    send_batches_count = Column(Integer, nullable=True)

    had_pauses = Column(Boolean, nullable=True)
    pause_count = Column(Integer, nullable=True)
    longest_pause_ms = Column(Integer, nullable=True)

    suspicion_score = Column(Integer, nullable=False, default=0)
    confidence = Column(Float, nullable=True)
    is_suspicious = Column(Boolean, nullable=False, default=False)

    reason = Column(String(128), nullable=True)
    flags_json = Column(JSON, nullable=True)
    raw_payload_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    attempt = relationship("PvpChallengeAttempt", lazy="selectin")
    challenger = relationship("User", foreign_keys=[challenger_id], lazy="selectin")
    opponent = relationship("User", foreign_keys=[opponent_id], lazy="selectin")

    __table_args__ = (
        CheckConstraint("reported_clicks >= 0", name="ck_pvp_ch_tel_reported_nonneg"),
        CheckConstraint("validated_clicks >= 0", name="ck_pvp_ch_tel_validated_nonneg"),
        CheckConstraint("(tap_count IS NULL) OR (tap_count >= 0)", name="ck_pvp_ch_tel_tap_count_nonneg"),
        CheckConstraint(
            "(max_concurrent_touches IS NULL) OR (max_concurrent_touches >= 0)",
            name="ck_pvp_ch_tel_touches_nonneg",
        ),
        CheckConstraint(
            "(avg_taps_per_sec IS NULL) OR (avg_taps_per_sec >= 0)",
            name="ck_pvp_ch_tel_avg_tps_nonneg",
        ),
        CheckConstraint(
            "(peak_taps_per_sec IS NULL) OR (peak_taps_per_sec >= 0)",
            name="ck_pvp_ch_tel_peak_tps_nonneg",
        ),
        CheckConstraint(
            "(pause_count IS NULL) OR (pause_count >= 0)",
            name="ck_pvp_ch_tel_pause_count_nonneg",
        ),
        CheckConstraint(
            "(longest_pause_ms IS NULL) OR (longest_pause_ms >= 0)",
            name="ck_pvp_ch_tel_longest_pause_nonneg",
        ),
        Index("ix_pvp_ch_tel_challenger_created", "challenger_id", "created_at"),
        Index("ix_pvp_ch_tel_suspicious", "is_suspicious", "created_at"),
    )


class PvpCheatEvent(Base):
    __tablename__ = "pvp_cheat_events"

    id = Column(Integer, primary_key=True)

    mode = Column(String(16), nullable=False)  # live | challenge
    event_code = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default="medium")  # low | medium | high | critical

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    session_id = Column(Integer, ForeignKey("pvp_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    attempt_id = Column(Integer, ForeignKey("pvp_challenge_attempts.id", ondelete="CASCADE"), nullable=True, index=True)

    reason = Column(String(128), nullable=True)
    details_json = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    user = relationship("User", lazy="selectin")
    session = relationship("PvpSession", lazy="selectin")
    attempt = relationship("PvpChallengeAttempt", lazy="selectin")

    __table_args__ = (
        CheckConstraint("(mode IN ('live','challenge'))", name="ck_pvp_cheat_events_mode_allowed"),
        CheckConstraint(
            "(severity IN ('low','medium','high','critical'))",
            name="ck_pvp_cheat_events_severity_allowed",
        ),
        CheckConstraint(
            "((session_id IS NOT NULL) OR (attempt_id IS NOT NULL))",
            name="ck_pvp_cheat_events_target_present",
        ),
        Index("ix_pvp_cheat_events_user_created", "user_id", "created_at"),
    )

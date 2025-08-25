# app/models/db_challenge.py
from sqlalchemy import Table, Column, BigInteger, Integer, Boolean, CHAR, TIMESTAMP, MetaData
from sqlalchemy.dialects.postgresql import BIGINT
from app.database import Base

metadata = Base.metadata

challenge_user_progress = Table(
    "challenge_user_progress",
    metadata,
    Column("id", BIGINT, primary_key=True),
    Column("user_id", BIGINT, nullable=False),  # FK на users(id)
    Column("day_index", Integer, nullable=False),
    Column("watched", Boolean, nullable=False),
    Column("watched_rewarded", Boolean, nullable=False),
    Column("answered", Boolean, nullable=False),
    Column("selected_option", CHAR(1)),
    Column("is_correct", Boolean),
    Column("answer_rewarded", Boolean, nullable=False),
    Column("codeword_revealed", Boolean, nullable=False),
    Column("created_at", TIMESTAMP, nullable=False),
    Column("updated_at", TIMESTAMP, nullable=False),
)

challenge_user_final = Table(
    "challenge_user_final",
    metadata,
    Column("id", BIGINT, primary_key=True),
    Column("user_id", BIGINT, nullable=False),  # FK на users(id)
    Column("submitted", Boolean, nullable=False),
    Column("success", Boolean, nullable=False),
    Column("reward_granted", Boolean, nullable=False),
    Column("submitted_at", TIMESTAMP),
    Column("updated_at", TIMESTAMP, nullable=False),
    Column("started_at", TIMESTAMP),  # 🔹 новое поле, соответствует миграции
)


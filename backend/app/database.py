# app/database.py
import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ⬇️ для sync-части (бот)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker as sync_sessionmaker

load_dotenv()

# ---- URLs ----
# Пример: DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/dbname"
DATABASE_URL = os.getenv("DATABASE_URL")

# Если хочешь задать sync-DSN явно, можно через переменную окружения:
# SYNC_DATABASE_URL="postgresql://user:pass@host:5432/dbname"
SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# Если SYNC_DATABASE_URL не задан, получим его из async-DSN, убрав '+asyncpg'
if not SYNC_DATABASE_URL:
    if "+asyncpg" in DATABASE_URL:
        SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")
    else:
        # на случай если изначально уже обычный postgresql://
        SYNC_DATABASE_URL = DATABASE_URL

# ---- Async engine/session (FastAPI) ----
async_engine = create_async_engine(
    DATABASE_URL,
    echo=False,            # можешь включить True для детального логгинга
    pool_pre_ping=True,
    future=True,
)

async_session_maker = sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ---- Sync engine/session (бот) ----
# Требуется пакет psycopg2-binary в requirements.txt
# psycopg2-binary>=2.9
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sync_sessionmaker(
    bind=sync_engine,
    autoflush=False,
    autocommit=False,
)

# ---- Base ----
Base = declarative_base()

# ---- DI helper for FastAPI ----
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

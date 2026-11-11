import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Создание движка
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required; see backend/.env.example")
engine = create_async_engine(DATABASE_URL, echo=False)

# Сессия
async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Базовая модель
Base = declarative_base()

# Функция получения сессии
async def get_async_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session

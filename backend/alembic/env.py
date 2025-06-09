import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import os
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

# Alembic Config
config = context.config
fileConfig(config.config_file_name)

# Импортируем Base и модели
from app.database import Base
from app.models import user  # добавляй сюда другие модели по мере необходимости

target_metadata = Base.metadata

# Устанавливаем URL из .env
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def do_migrations():
        async with connectable.connect() as connection:
            await connection.run_sync(
                lambda conn: context.configure(
                    connection=conn,
                    target_metadata=target_metadata,
                    compare_type=True,
                )
            )
            await connection.run_sync(lambda _: context.run_migrations())

    asyncio.run(do_migrations())



if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

import sys
import os
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

config = context.config
fileConfig(config.config_file_name)

from app.database import Base
from app.models.user import User

target_metadata = Base.metadata
_ = User

config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="public",
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
                    include_schemas=True,
                    version_table_schema="public",
                )
            )
            await connection.run_sync(lambda _: context.run_migrations())

    asyncio.run(do_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

print("[ALEMBIC] Using DATABASE_URL:", os.getenv("DATABASE_URL"))





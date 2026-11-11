import asyncio
import importlib
import pkgutil
from app import models
from app.database import engine, Base
from app.models.user import User  # ⬅️ обязательно прямой импорт
from sqlalchemy.exc import SQLAlchemyError

async def init_models():
    try:
        for module in pkgutil.iter_modules(models.__path__):
            importlib.import_module(f"app.models.{module.name}")
        async with engine.begin() as conn:
            print("🔧 Создаём таблицы...")
            await conn.run_sync(Base.metadata.create_all)
            print("✅ Таблицы успешно созданы.")
    except SQLAlchemyError as e:
        raise RuntimeError("Failed to initialize the development database") from e

if __name__ == "__main__":
    asyncio.run(init_models())

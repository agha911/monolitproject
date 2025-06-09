import asyncio
from app.database import engine, Base
from app.models.user import User  # ⬅️ обязательно прямой импорт
from sqlalchemy.exc import SQLAlchemyError

async def init_models():
    try:
        async with engine.begin() as conn:
            print("🔧 Создаём таблицы...")
            await conn.run_sync(Base.metadata.create_all)
            print("✅ Таблицы успешно созданы.")
    except SQLAlchemyError as e:
        print(f"❌ Ошибка при создании таблиц: {e}")

if __name__ == "__main__":
    asyncio.run(init_models())

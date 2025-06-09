import asyncio
from app.database import engine, Base
from app.models.user import User  # ⬅️ обязательно прямой импорт

async def init_models():
    async with engine.begin() as conn:
        print("🔧 Создаём таблицы...")
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Таблицы успешно созданы.")

if __name__ == "__main__":
    asyncio.run(init_models())

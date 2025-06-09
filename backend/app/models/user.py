from sqlalchemy import Column, Integer, String, DateTime, JSON
from app.database import Base  # ✅ используем общую базу
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    first_name = Column(String)
    last_name = Column(String)
    score = Column(Integer, default=0)
    xp = Column(Integer, default=0)
    total_xp = Column(Integer, default=0)
    level = Column(Integer, default=1)
    energy = Column(Integer, default=100)
    max_energy = Column(Integer, default=100)
    lastEnergyUpdate = Column(DateTime, nullable=True)
    last_checkin = Column(DateTime, nullable=True)
    daily_streak = Column(Integer, default=0)
    completed_tasks = Column(JSON, default=[])



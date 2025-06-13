from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base  # ✅ используем общую базу
from datetime import datetime
from sqlalchemy import BigInteger

class User(Base):
    __tablename__ = "users"
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)  
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
    invited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    invites_count = Column(Integer, default=0)
    inviter = relationship("User", remote_side=[id], backref="invited_users")
    energy_notified = Column(Boolean, default=False)


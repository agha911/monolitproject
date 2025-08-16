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
    total_xp = Column(Integer, default=0)
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
    energy_refill_count = Column(Integer, default=0)
    last_energy_refill = Column(DateTime, nullable=True)
    click_boost_level = Column(Integer, default=0)
    invited_at = Column(DateTime, nullable=True)
    joined_group = Column(Boolean, default=False)
    daily_target = Column(Integer, default=0)
    daily_progress = Column(Integer, default=0)
    daily_completed = Column(Boolean, default=False)
    daily_updated_at = Column(DateTime, default=None)
    daily_reward_claimed = Column(Boolean, default=False)
    tournament_clicks = Column(Integer, default=0, nullable=False)
    tournament_updated_at = Column(DateTime, default=datetime.utcnow)
    last_client_seq = Column(Integer, nullable=False, server_default="0")
    energy_upgrade_count = Column(Integer, default=0)
    last_energy_upgrade = Column(DateTime, nullable=True)
    partner_task_claimed_id = Column(String(64), nullable=True, index=True)
    
    


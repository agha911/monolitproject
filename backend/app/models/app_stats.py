from sqlalchemy import Column, Integer, BigInteger
from app.database import Base

class AppStats(Base):
    __tablename__ = "app_stats"

    id = Column(Integer, primary_key=True)
    total_spent = Column(BigInteger, default=0)

# app/models/db_tournament_winner.py
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, BigInteger, SmallInteger, Text, DateTime,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from app.database import Base        # поправь путь под свой проект
from app.models.user import User        # поправь путь под свой проект

LeagueEnum = PGEnum('bronze', 'silver', 'gold', name='league_enum', create_type=False)

class TournamentWinner(Base):
    __tablename__ = "tournament_winners"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Наивные UTC-даты (как и в твоей User-модели)
    period_start = Column(DateTime, nullable=False)
    period_end   = Column(DateTime,   nullable=False)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user    = relationship("User")

    username_snapshot = Column(Text)
    league            = Column(LeagueEnum, nullable=False)
    rank_in_league    = Column(SmallInteger, nullable=False)
    clicks_snapshot   = Column(BigInteger, nullable=False)

    trc20_address: Optional[str] = Column(Text)
    gift_choice:   Optional[str] = Column(Text)
    tshirt_size:   Optional[str] = Column(Text)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('period_start','period_end','league','rank_in_league', name='uq_tw_period_league_rank'),
        UniqueConstraint('period_start','period_end','league','user_id',       name='uq_tw_period_league_user'),
        Index('ix_tw_period_league', 'period_start','period_end','league'),
    )

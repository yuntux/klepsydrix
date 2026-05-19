from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class PeriodType(Base):
    __tablename__ = "period_types"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(50), nullable=False, unique=True)

    # Relations de navigation
    periods = relationship("Period", back_populates="period_type", passive_deletes="all")

from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class PeriodType(Base):
    __tablename__ = "period_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, info={"label": "Libellé du type de période", "placeholder": "ex: Trimestre"})

    # Relations de navigation
    periods: Mapped[list["Period"]] = relationship("Period", back_populates="period_type", passive_deletes="all")

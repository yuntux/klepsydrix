from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Period(Base):
    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    period_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("period_types.id", ondelete="CASCADE"), nullable=False, info={"label": "Type de Période"})
    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de la période", "placeholder": "ex: S1"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom de la période", "placeholder": "ex: Semestre 1"})
    start_date: Mapped[date] = mapped_column(Date, nullable=False, info={"label": "Date de début"})
    end_date: Mapped[date] = mapped_column(Date, nullable=False, info={"label": "Date de fin"})

    # Relations de navigation
    period_type: Mapped[Optional["PeriodType"]] = relationship("PeriodType", back_populates="periods")
    school: Mapped[Optional["School"]] = relationship("School", back_populates="periods")


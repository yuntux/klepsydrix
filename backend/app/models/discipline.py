from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Discipline(Base):
    __tablename__ = "disciplines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de la discipline", "placeholder": "ex: L0100"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom complet", "placeholder": "ex: Mathématiques"})

    # Relations de navigation
    subjects: Mapped[list["Subject"]] = relationship("Subject", back_populates="discipline", passive_deletes="all")
    trmd_budgets: Mapped[list["TrmdBudget"]] = relationship("TrmdBudget", back_populates="discipline", passive_deletes="all")

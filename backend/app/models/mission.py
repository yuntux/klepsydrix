from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de la mission", "placeholder": "ex: PP"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom complet", "placeholder": "ex: Professeur Principal"})
    hours_allowance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, info={"label": "Heures allouées", "min": 0, "max": 40, "step": "0.5"})

    # Relations de navigation
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="mission", info={"label": "Cours"})

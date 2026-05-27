from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Alternation(Base):
    __tablename__ = "alternations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de l'alternance", "placeholder": "ex: Q1"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom de l'alternance", "placeholder": "ex: Quinzaine 1"})
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, info={"label": "Couleur", "type": "color", "placeholder": "ex: #F59E0B"})

    # Relations de navigation
    # Les préférences et contraintes se lient via des tables associatives Many-to-Many

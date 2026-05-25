from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False, info={"label": "Code du matériel", "placeholder": "ex: IPAD"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom du matériel", "placeholder": "ex: Valise iPad Pro"})
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, info={"label": "Quantité disponible", "min": 1, "max": 500})

    # Relations de navigation
    # Noter que l'association avec les sessions se fait via session_materials (Many-to-Many)

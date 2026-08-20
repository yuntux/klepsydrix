from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Material(Base):
    __tablename__ = "materials"

    # Impression PDF (voir architecture.md §22, reports/timetable.py) — voir Teacher pour le
    # commentaire complet, même patron mutualisé sur les 7 ressources liées à un cours.
    __actions__ = [
        {
            "id": "print_timetable",
            "label": "Imprimer l'emploi du temps",
            "type": "report",
            "icon": "fa-print",
            "report": "timetable_material",
        },
    ]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False, info={"label": "Code du matériel", "placeholder": "ex: IPAD"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom du matériel", "placeholder": "ex: Valise iPad Pro"})
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, info={"label": "Quantité disponible", "min": 1, "max": 500})

    # Relations de navigation
    # Noter que l'association avec les sessions se fait via session_materials (Many-to-Many)

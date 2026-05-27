from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(15), unique=True, index=True, nullable=False, info={"label": "Code de la matière", "placeholder": "ex: MATHS"})
    code_nomenclature: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False, info={"label": "Code nomenclature", "placeholder": "ex: 006600"})
    short_name: Mapped[str] = mapped_column(String(30), nullable=False, info={"label": "Libellé court", "placeholder": "ex: Maths"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Libellé long", "placeholder": "ex: Mathématiques"})
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#CCCCCC", info={"label": "Code couleur", "type": "color", "placeholder": "ex: #3498DB"})
    is_etp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, info={"label": "Matière ETP"})
    is_specialty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Matière de Spécialité"})
    pedagogic_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, info={"label": "Poids Pédagogique", "min": 0.1, "max": 10.0, "step": "0.1"})
    
    discipline_id: Mapped[int] = mapped_column(Integer, ForeignKey("disciplines.id", ondelete="RESTRICT"), nullable=False, info={"label": "Discipline"})
    family_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("families.id", ondelete="SET NULL"), nullable=True, info={"label": "Famille"})

    # Relations de navigation
    discipline: Mapped[Optional["Discipline"]] = relationship("Discipline", back_populates="subjects")
    family: Mapped[Optional["Family"]] = relationship("Family", back_populates="subjects")
    mef_services: Mapped[list["MefService"]] = relationship("MefService", back_populates="subject", passive_deletes="all", info={"label": "Services MEF"})
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="subject_relation", passive_deletes="all", info={"label": "Cours"})

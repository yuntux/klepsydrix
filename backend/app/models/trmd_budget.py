from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, ForeignKey, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class TrmdBudget(Base):
    __tablename__ = "trmd_budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    discipline_id: Mapped[int] = mapped_column(Integer, ForeignKey("disciplines.id", ondelete="CASCADE"), nullable=False, info={"label": "Discipline"})
    allocated_hp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, info={"label": "Heures Postes (HP)", "min": 0.0, "max": 1000.0, "step": "0.5"}) # Heures Postes
    allocated_hsa: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, info={"label": "Heures Supp. Annuelles (HSA)", "min": 0.0, "max": 1000.0, "step": "0.5"}) # Heures Supplémentaires Annuelles
    allocated_posts: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, info={"label": "Postes budgétés (ETP)", "min": 0.0, "max": 100.0, "step": "0.1"}) # ETP

    # Contrainte d'unicité sur le couple school_id, discipline_id
    __table_args__ = (
        UniqueConstraint("school_id", "discipline_id", name="uq_school_discipline_budget"),
    )

    # Relations de navigation
    school: Mapped[Optional["School"]] = relationship("School")
    discipline: Mapped[Optional["Discipline"]] = relationship("Discipline", back_populates="trmd_budgets")

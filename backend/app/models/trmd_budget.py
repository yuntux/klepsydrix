from sqlalchemy import Column, Integer, ForeignKey, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class TrmdBudget(Base):
    __tablename__ = "trmd_budgets"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    discipline_id = Column(Integer, ForeignKey("disciplines.id", ondelete="CASCADE"), nullable=False)
    allocated_hp = Column(Float, nullable=False, default=0.0) # Heures Postes
    allocated_hsa = Column(Float, nullable=False, default=0.0) # Heures Supplémentaires Annuelles
    allocated_posts = Column(Float, nullable=False, default=0.0) # ETP

    # Contrainte d'unicité sur le couple school_id, discipline_id
    __table_args__ = (
        UniqueConstraint("school_id", "discipline_id", name="uq_school_discipline_budget"),
    )

    # Relations de navigation
    school = relationship("School")
    discipline = relationship("Discipline", back_populates="trmd_budgets")

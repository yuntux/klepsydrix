from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Discipline(Base):
    __tablename__ = "disciplines"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de la discipline", "placeholder": "ex: L0100"})
    name = Column(String(100), nullable=False, info={"label": "Nom complet", "placeholder": "ex: Mathématiques"})

    # Relations de navigation
    subjects = relationship("Subject", back_populates="discipline", passive_deletes="all")
    trmd_budgets = relationship("TrmdBudget", back_populates="discipline", passive_deletes="all")

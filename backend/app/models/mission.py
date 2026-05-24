from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Mission(Base):
    __tablename__ = "missions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de la mission", "placeholder": "ex: PP"})
    name = Column(String(100), nullable=False, info={"label": "Nom complet", "placeholder": "ex: Professeur Principal"})
    hours_allowance = Column(Float, nullable=False, default=0.0, info={"label": "Heures allouées", "min": 0, "max": 40, "step": "0.5"})

    # Relations de navigation
    courses = relationship("Course", back_populates="mission")

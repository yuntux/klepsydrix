from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Classroom(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False, info={"label": "Code de la salle", "placeholder": "ex: S101"})
    name = Column(String(50), nullable=False, info={"label": "Nom de la salle", "placeholder": "ex: Salle 101"})
    capacity = Column(Integer, nullable=False, default=35, info={"label": "Capacité de places", "min": 1, "max": 200})
    quantity = Column(Integer, nullable=False, default=1, info={"label": "Quantité", "min": 1, "max": 10}) # > 1 = groupe de salles
    
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)

    # Relations de navigation
    school = relationship("School", back_populates="classrooms")
    site = relationship("Site", back_populates="classrooms")


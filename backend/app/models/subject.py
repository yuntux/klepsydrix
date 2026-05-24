from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(15), unique=True, index=True, nullable=False, info={"label": "Code de la matière", "placeholder": "ex: MATHS"})
    code_nomenclature = Column(String(20), unique=True, index=True, nullable=False, info={"label": "Code nomenclature", "placeholder": "ex: 006600"})
    short_label = Column(String(30), nullable=False, info={"label": "Libellé court", "placeholder": "ex: Maths"})
    long_label = Column(String(100), nullable=False, info={"label": "Libellé long", "placeholder": "ex: Mathématiques"})
    color = Column(String(7), nullable=False, default="#CCCCCC", info={"label": "Code couleur", "type": "color", "placeholder": "ex: #3498DB"})
    is_etp = Column(Boolean, nullable=False, default=True, info={"label": "Matière ETP"})
    is_specialty = Column(Boolean, nullable=False, default=False, info={"label": "Matière de Spécialité"})
    pedagogic_weight = Column(Float, nullable=False, default=1.0, info={"label": "Poids Pédagogique", "min": 0.1, "max": 10.0, "step": "0.1"})
    
    discipline_id = Column(Integer, ForeignKey("disciplines.id", ondelete="RESTRICT"), nullable=False)
    family_id = Column(Integer, ForeignKey("families.id", ondelete="SET NULL"), nullable=True)

    # Relations de navigation
    discipline = relationship("Discipline", back_populates="subjects")
    family = relationship("Family", back_populates="subjects")
    mef_services = relationship("MefService", back_populates="subject", passive_deletes="all")
    courses = relationship("Course", back_populates="subject_relation", passive_deletes="all")

from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(15), unique=True, index=True, nullable=False)
    code_nomenclature = Column(String(20), unique=True, index=True, nullable=False)
    short_label = Column(String(30), nullable=False)
    long_label = Column(String(100), nullable=False)
    color = Column(String(7), nullable=False, default="#CCCCCC")
    is_etp = Column(Boolean, nullable=False, default=True)
    is_specialty = Column(Boolean, nullable=False, default=False)
    pedagogic_weight = Column(Float, nullable=False, default=1.0)
    
    discipline_id = Column(Integer, ForeignKey("disciplines.id", ondelete="RESTRICT"), nullable=False)
    family_id = Column(Integer, ForeignKey("families.id", ondelete="SET NULL"), nullable=True)

    # Relations de navigation
    discipline = relationship("Discipline", back_populates="subjects")
    family = relationship("Family", back_populates="subjects")
    mef_services = relationship("MefService", back_populates="subject", passive_deletes="all")
    courses = relationship("Course", back_populates="subject_relation", passive_deletes="all")

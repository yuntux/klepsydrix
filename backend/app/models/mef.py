from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Mef(Base):
    __tablename__ = "mefs"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    code_national = Column(String(11), unique=True, index=True, nullable=False)
    label = Column(String(100), nullable=False)
    forecast_student_count = Column(Integer, nullable=False, default=0)
    max_students_per_class = Column(Integer, nullable=False, default=30)

    # Relations de navigation
    school = relationship("School")
    mef_services = relationship("MefService", back_populates="mef", passive_deletes="all")
    divisions = relationship("Division", back_populates="mef")

class MefService(Base):
    __tablename__ = "mef_services"

    id = Column(Integer, primary_key=True, index=True)
    mef_id = Column(Integer, ForeignKey("mefs.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    weekly_hours = Column(Float, nullable=False, default=0.0)

    # Relations de navigation
    mef = relationship("Mef", back_populates="mef_services")
    subject = relationship("Subject", back_populates="mef_services")

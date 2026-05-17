from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True, index=True)
    uai = Column(String(8), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    standard_timeslot_duration = Column(Integer, nullable=False, default=30)

    # Relations de navigation
    teachers = relationship("Teacher", back_populates="school", passive_deletes="all")
    divisions = relationship("Division", back_populates="school", passive_deletes="all")
    classrooms = relationship("Classroom", back_populates="school", passive_deletes="all")
    courses = relationship("Course", back_populates="school", passive_deletes="all")
    sessions = relationship("Session", back_populates="school", passive_deletes="all")

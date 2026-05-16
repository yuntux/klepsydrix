from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(100), nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)

    # Clés étrangères
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="RESTRICT"), nullable=False)
    classroom_id = Column(Integer, ForeignKey("classrooms.id", ondelete="RESTRICT"), nullable=True)
    timeslot_id = Column(Integer, ForeignKey("timeslots.id", ondelete="RESTRICT"), nullable=True)

    # Relations de navigation de l'ORM
    teacher = relationship("Teacher", back_populates="courses")
    division = relationship("Division", back_populates="courses")
    classroom = relationship("Classroom", back_populates="courses")
    timeslot = relationship("Timeslot", back_populates="courses")

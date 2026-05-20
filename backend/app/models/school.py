from sqlalchemy import Column, Integer, String, Date
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True, index=True)
    uai = Column(String(8), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    student_start_date = Column(Date, nullable=True)
    student_end_date = Column(Date, nullable=True)

    # Relations de navigation
    teachers = relationship("Teacher", back_populates="school", passive_deletes="all")
    divisions = relationship("Division", back_populates="school", passive_deletes="all")
    classrooms = relationship("Classroom", back_populates="school", passive_deletes="all")
    courses = relationship("Course", back_populates="school", passive_deletes="all")
    sessions = relationship("Session", back_populates="school", passive_deletes="all")
    periods = relationship("Period", back_populates="school", passive_deletes="all")

    @classmethod
    def test_class_method(cls, db, multiplier: int):
        return db.query(cls).count() * multiplier

    def test_instance_method(self, db, prefix: str):
        return f"{prefix} {self.name}"

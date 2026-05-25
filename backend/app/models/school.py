from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Date
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class School(Base):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uai: Mapped[str] = mapped_column(String(8), unique=True, index=True, nullable=False, info={"label": "Code UAI (RNE)", "placeholder": "ex: 0750001A"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom de l'établissement", "placeholder": "ex: Collège Jean Jaurès"})
    student_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de rentrée des élèves"})
    student_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de sortie des élèves"})

    # Relations de navigation
    teachers: Mapped[list["Teacher"]] = relationship("Teacher", back_populates="school", passive_deletes="all")
    divisions: Mapped[list["Division"]] = relationship("Division", back_populates="school", passive_deletes="all")
    classrooms: Mapped[list["Classroom"]] = relationship("Classroom", back_populates="school", passive_deletes="all")
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="school", passive_deletes="all")

    periods: Mapped[list["Period"]] = relationship("Period", back_populates="school", passive_deletes="all")

    @classmethod
    def test_class_method(cls, db, multiplier: int):
        return db.query(cls).count() * multiplier

    def test_instance_method(self, db, prefix: str):
        return f"{prefix} {self.name}"

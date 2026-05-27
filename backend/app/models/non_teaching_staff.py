from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class NonTeachingStaff(Base):
    __tablename__ = "non_teaching_staffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Prénom", "placeholder": "ex: Jean"})
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom de famille", "placeholder": "ex: Dupont"})
    role: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Rôle / Fonction", "placeholder": "ex: AESH"})
    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})

    courses: Mapped[list["Course"]] = relationship("Course", secondary="course_non_teaching_staffs", back_populates="non_teaching_staffs", passive_deletes="all", info={"label": "Cours"})

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

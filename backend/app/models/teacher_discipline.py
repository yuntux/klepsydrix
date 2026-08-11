from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, ForeignKey
from backend.app.models.base import Base


class TeacherDiscipline(Base):
    __tablename__ = "teacher_disciplines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    discipline_id: Mapped[int] = mapped_column(Integer, ForeignKey("disciplines.id", ondelete="RESTRICT"), nullable=False, info={"label": "Discipline"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée (min)", "min": 0})

    # Relations de navigation
    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="discipline_lines")
    discipline: Mapped["Discipline"] = relationship("Discipline")

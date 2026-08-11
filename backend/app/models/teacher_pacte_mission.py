from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, ForeignKey
from backend.app.models.base import Base


class TeacherPacteMission(Base):
    __tablename__ = "teacher_pacte_missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    ref_pacte_mission_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_pacte_missions.id", ondelete="RESTRICT"), nullable=False, info={"label": "Mission Pacte"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée (min)", "min": 0})

    # Relations de navigation
    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="pacte_mission_lines")
    ref_pacte_mission: Mapped["RefPacteMission"] = relationship("RefPacteMission")

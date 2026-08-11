from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, ForeignKey
from backend.app.models.base import Base


class TeacherParticularMission(Base):
    __tablename__ = "teacher_particular_missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    ref_particular_mission_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_particular_missions.id", ondelete="RESTRICT"), nullable=False, info={"label": "Mission particulière"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée (min)", "min": 0})

    # Relations de navigation
    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="particular_mission_lines")
    ref_particular_mission: Mapped["RefParticularMission"] = relationship("RefParticularMission")

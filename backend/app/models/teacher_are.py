from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, ForeignKey
from backend.app.models.base import Base


class TeacherAre(Base):
    __tablename__ = "teacher_ares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    ref_are_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_ares.id", ondelete="RESTRICT"), nullable=False, info={"label": "ARE"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée (min)", "min": 0})

    # Relations de navigation
    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="are_lines")
    ref_are: Mapped["RefAre"] = relationship("RefAre")

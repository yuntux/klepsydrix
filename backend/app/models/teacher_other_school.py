from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, ForeignKey
from backend.app.models.base import Base


class TeacherOtherSchool(Base):
    __tablename__ = "teacher_other_schools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    ref_external_school_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_external_schools.id", ondelete="RESTRICT"), nullable=False, info={"label": "Autre établissement"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée (min)", "min": 0})

    # Relations de navigation
    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="other_school_lines")
    ref_external_school: Mapped["RefExternalSchool"] = relationship("RefExternalSchool")

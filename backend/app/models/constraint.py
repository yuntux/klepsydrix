from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class ResourceConstraint(Base):
    __tablename__ = "resource_constraints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False) # 'Subject', 'Teacher', 'Division', 'Classroom', 'Site'
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # Nullable : si NULL, s'applique à toutes les ressources de ce type

    # Attributs Matières (Subject)
    target_subject_b_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True)
    incompatible_same_half_day: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    incompatible_same_day: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    incompatible_two_consecutive_days: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    min_free_half_days_between: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prevent_consecutive_a_then_b: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    prevent_consecutive_b_then_a: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    max_hours_per_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_hours_per_half_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weekly_order_a_before_b: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    weekly_order_b_before_a: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    group_course_order: Mapped[Optional[str]] = mapped_column(String(30), default="NONE") # 'NONE', 'GROUP_BEFORE', 'GROUP_AFTER', 'GROUP_BEFORE_OR_AFTER', 'GROUP_BEFORE_OR_AFTER_FORTNIGHT'

    # Attributs Profs et Classes (Teacher / Division)
    max_hours_per_am: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_hours_per_pm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_presence_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_presence_hours_per_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    late_start_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    late_start_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True) # ex: '09:00'
    early_end_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    early_end_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True) # ex: '16:30'
    min_free_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_free_half_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_worked_am_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_worked_pm_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    only_one_half_day_per_day: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    max_gap_hours_per_week: Mapped[Optional[int]] = mapped_column(Integer, default=2)

    # Attributs Site
    max_travel_trips_per_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Navigation
    target_subject_b: Mapped[Optional["Subject"]] = relationship("Subject", foreign_keys=[target_subject_b_id])

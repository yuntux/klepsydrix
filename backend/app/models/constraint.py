from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, Table
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

# Table de jointure Many-to-Many pour Constraint <-> Alternation
constraint_alternations = Table(
    "constraint_alternations",
    Base.metadata,
    Column("constraint_id", Integer, ForeignKey("resource_constraints.id", ondelete="CASCADE"), primary_key=True),
    Column("alternation_id", Integer, ForeignKey("alternations.id", ondelete="CASCADE"), primary_key=True)
)

class ResourceConstraint(Base):
    __tablename__ = "resource_constraints"

    id = Column(Integer, primary_key=True, index=True)
    resource_type = Column(String(30), nullable=False) # 'Subject', 'Teacher', 'Division', 'Classroom', 'Site'
    resource_id = Column(Integer, nullable=True) # Nullable : si NULL, s'applique à toutes les ressources de ce type

    # Attributs Matières (Subject)
    target_subject_b_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True)
    incompatible_same_half_day = Column(Boolean, default=False)
    incompatible_same_day = Column(Boolean, default=False)
    incompatible_two_consecutive_days = Column(Boolean, default=False)
    min_free_half_days_between = Column(Integer, nullable=True)
    prevent_consecutive_a_then_b = Column(Boolean, default=False)
    prevent_consecutive_b_then_a = Column(Boolean, default=False)
    max_hours_per_day = Column(Float, nullable=True)
    max_hours_per_half_day = Column(Float, nullable=True)
    weekly_order_a_before_b = Column(Boolean, default=False)
    weekly_order_b_before_a = Column(Boolean, default=False)
    group_course_order = Column(String(30), default="NONE") # 'NONE', 'GROUP_BEFORE', 'GROUP_AFTER', 'GROUP_BEFORE_OR_AFTER', 'GROUP_BEFORE_OR_AFTER_FORTNIGHT'

    # Attributs Profs et Classes (Teacher / Division)
    max_hours_per_am = Column(Float, nullable=True)
    max_hours_per_pm = Column(Float, nullable=True)
    max_presence_days_per_week = Column(Integer, nullable=True)
    max_presence_hours_per_day = Column(Float, nullable=True)
    late_start_days_per_week = Column(Integer, nullable=True)
    late_start_time = Column(String(5), nullable=True) # ex: '09:00'
    early_end_days_per_week = Column(Integer, nullable=True)
    early_end_time = Column(String(5), nullable=True) # ex: '16:30'
    min_free_days_per_week = Column(Integer, nullable=True)
    min_free_half_days_per_week = Column(Integer, nullable=True)
    max_worked_am_per_week = Column(Integer, nullable=True)
    max_worked_pm_per_week = Column(Integer, nullable=True)
    only_one_half_day_per_day = Column(Boolean, default=False)
    max_gap_hours_per_week = Column(Integer, default=2)

    # Attributs Site
    max_travel_trips_per_day = Column(Integer, nullable=True)

    # Navigation
    target_subject_b = relationship("Subject", foreign_keys=[target_subject_b_id])
    alternations = relationship("Alternation", secondary=constraint_alternations)

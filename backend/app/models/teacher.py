from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship, Session
from backend.app.models.base import Base, related_field

class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False)
    first_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False) # ex: 'M. Martin' (compatibilité V1)
    max_weekly_hours = Column(Float, nullable=False, default=18.0)
    
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)

    # Relations de navigation
    school = relationship("School", back_populates="teachers")
    courses = relationship("Course", secondary="course_teachers", back_populates="teachers", passive_deletes="all")
    # Noter que l'association avec les sessions se fait via session_teachers (Many-to-Many)

    # Déclaration déclarative et compacte des champs liés (Style Odoo)
    max_hours_per_day = related_field("constraint_record", "max_hours_per_day")
    max_hours_per_am = related_field("constraint_record", "max_hours_per_am")
    max_hours_per_pm = related_field("constraint_record", "max_hours_per_pm")
    max_presence_days_per_week = related_field("constraint_record", "max_presence_days_per_week")
    max_presence_hours_per_day = related_field("constraint_record", "max_presence_hours_per_day")
    late_start_days_per_week = related_field("constraint_record", "late_start_days_per_week")
    late_start_time = related_field("constraint_record", "late_start_time")
    early_end_days_per_week = related_field("constraint_record", "early_end_days_per_week")
    early_end_time = related_field("constraint_record", "early_end_time")
    min_free_days_per_week = related_field("constraint_record", "min_free_days_per_week")
    min_free_half_days_per_week = related_field("constraint_record", "min_free_half_days_per_week")
    max_worked_am_per_week = related_field("constraint_record", "max_worked_am_per_week")
    max_worked_pm_per_week = related_field("constraint_record", "max_worked_pm_per_week")
    only_one_half_day_per_day = related_field("constraint_record", "only_one_half_day_per_day", default=False)
    max_gap_hours_per_week = related_field("constraint_record", "max_gap_hours_per_week", default=2)

    @property
    def constraint_record(self):
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if not session or not self.id:
            return None
        
        from backend.app.models.constraint import ResourceConstraint
        return session.query(ResourceConstraint).filter(
            ResourceConstraint.resource_type == 'Teacher',
            ResourceConstraint.resource_id == self.id
        ).first()

    def _ensure_constraint_record(self):
        """
        Méthode appelée automatiquement par le CRUDMixin parent pour
        garantir l'existence de la contrainte liée.
        """
        from backend.app.models.constraint import ResourceConstraint
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if not session:
            return None
            
        constraint = session.query(ResourceConstraint).filter(
            ResourceConstraint.resource_type == 'Teacher',
            ResourceConstraint.resource_id == self.id
        ).first()
        if not constraint:
            constraint = ResourceConstraint(
                resource_type='Teacher',
                resource_id=self.id
            )
            constraint._via_crud_mixin_create = True
            session.add(constraint)
        return constraint

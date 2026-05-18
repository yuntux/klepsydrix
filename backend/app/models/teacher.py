from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship, Session
from backend.app.models.base import Base

class related_field(property):
    """
    Subclass de property qui simule un champ 'related' à la Odoo dans SQLAlchemy.
    Permet la découverte dynamique des propriétés virtuelles.
    """
    def __init__(self, relation_name: str, target_field: str, default=None):
        self.relation_name = relation_name
        self.target_field = target_field
        self.default = default
        self._is_related = True

        def getter(instance):
            related_obj = getattr(instance, relation_name)
            if not related_obj:
                return default
            return getattr(related_obj, target_field, default)

        def setter(instance, value):
            related_obj = getattr(instance, relation_name)
            if related_obj:
                setattr(related_obj, target_field, value)

        super().__init__(getter, setter)

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
    courses = relationship("Course", back_populates="teacher", passive_deletes="all")
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

    # Surcharges CRUD pour persister dans resource_constraints
    @classmethod
    def create(cls, db: Session, vals: dict):
        constraint_vals = {}
        teacher_vals = {}
        for k, v in vals.items():
            if k in cls._fields:
                constraint_vals[k] = v
            else:
                teacher_vals[k] = v

        teacher = super().create(db, teacher_vals)

        from backend.app.models.constraint import ResourceConstraint
        constraint = db.query(ResourceConstraint).filter(
            ResourceConstraint.resource_type == 'Teacher',
            ResourceConstraint.resource_id == teacher.id
        ).first()
        if not constraint:
            constraint = ResourceConstraint(
                resource_type='Teacher',
                resource_id=teacher.id
            )
            db.add(constraint)

        for k, v in constraint_vals.items():
            setattr(constraint, k, v)
        
        db.commit()
        db.refresh(teacher)
        return teacher

    def update(self, db: Session, vals: dict):
        constraint_vals = {}
        teacher_vals = {}
        for k, v in vals.items():
            if k in self._fields:
                constraint_vals[k] = v
            else:
                teacher_vals[k] = v

        super().update(db, teacher_vals)

        if constraint_vals or True: # On force la création de l'enregistrement de contrainte s'il n'existe pas
            from backend.app.models.constraint import ResourceConstraint
            constraint = db.query(ResourceConstraint).filter(
                ResourceConstraint.resource_type == 'Teacher',
                ResourceConstraint.resource_id == self.id
            ).first()
            if not constraint:
                constraint = ResourceConstraint(
                    resource_type='Teacher',
                    resource_id=self.id
                )
                db.add(constraint)

            for k, v in constraint_vals.items():
                setattr(constraint, k, v)
            
            db.commit()
            db.refresh(self)

        return self

# Extraction dynamique et automatique de l'ensemble des champs Odoo-like liés
Teacher._fields = [
    name for name, attr in Teacher.__dict__.items()
    if isinstance(attr, property) and getattr(attr, "_is_related", False)
]

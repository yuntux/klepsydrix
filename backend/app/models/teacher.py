from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship, Session
from backend.app.models.base import Base

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

    # Champs virtuels de contraintes mappés sur la table resource_constraints (US3 / Preferences)
    _fields = [
        "max_hours_per_day",
        "max_hours_per_am",
        "max_hours_per_pm",
        "max_presence_days_per_week",
        "max_presence_hours_per_day",
        "late_start_days_per_week",
        "late_start_time",
        "early_end_days_per_week",
        "early_end_time",
        "min_free_days_per_week",
        "min_free_half_days_per_week",
        "max_worked_am_per_week",
        "max_worked_pm_per_week",
        "only_one_half_day_per_day",
        "max_gap_hours_per_week"
    ]

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

    # Propriétés virtuelles d'accès
    @property
    def max_hours_per_day(self):
        rec = self.constraint_record
        return rec.max_hours_per_day if rec else None

    @property
    def max_hours_per_am(self):
        rec = self.constraint_record
        return rec.max_hours_per_am if rec else None

    @property
    def max_hours_per_pm(self):
        rec = self.constraint_record
        return rec.max_hours_per_pm if rec else None

    @property
    def max_presence_days_per_week(self):
        rec = self.constraint_record
        return rec.max_presence_days_per_week if rec else None

    @property
    def max_presence_hours_per_day(self):
        rec = self.constraint_record
        return rec.max_presence_hours_per_day if rec else None

    @property
    def late_start_days_per_week(self):
        rec = self.constraint_record
        return rec.late_start_days_per_week if rec else None

    @property
    def late_start_time(self):
        rec = self.constraint_record
        return rec.late_start_time if rec else None

    @property
    def early_end_days_per_week(self):
        rec = self.constraint_record
        return rec.early_end_days_per_week if rec else None

    @property
    def early_end_time(self):
        rec = self.constraint_record
        return rec.early_end_time if rec else None

    @property
    def min_free_days_per_week(self):
        rec = self.constraint_record
        return rec.min_free_days_per_week if rec else None

    @property
    def min_free_half_days_per_week(self):
        rec = self.constraint_record
        return rec.min_free_half_days_per_week if rec else None

    @property
    def max_worked_am_per_week(self):
        rec = self.constraint_record
        return rec.max_worked_am_per_week if rec else None

    @property
    def max_worked_pm_per_week(self):
        rec = self.constraint_record
        return rec.max_worked_pm_per_week if rec else None

    @property
    def only_one_half_day_per_day(self):
        rec = self.constraint_record
        return rec.only_one_half_day_per_day if rec else False

    @property
    def max_gap_hours_per_week(self):
        rec = self.constraint_record
        return rec.max_gap_hours_per_week if rec else 2

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

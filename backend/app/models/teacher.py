from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship, Session
from backend.app.models.base import Base, related_field

class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False, info={"label": "Code Enseignant", "placeholder": "ex: T1"})
    first_name = Column(String(50), nullable=True, info={"label": "Prénom", "placeholder": "ex: Marc"})
    last_name = Column(String(50), nullable=False, info={"label": "Nom de famille", "placeholder": "ex: Dupont"})
    name = Column(String(100), nullable=False, info={"label": "Nom d'usage complet", "placeholder": "ex: M. Dupont"}) # ex: 'M. Martin' (compatibilité V1)
    max_weekly_hours = Column(Float, nullable=False, default=18.0, info={"label": "Heures max hebdomadaires", "min": 1.0, "max": 40.0, "step": "0.5"})
    
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement Principal"})

    # Relations de navigation
    school = relationship("School", back_populates="teachers")
    courses = relationship("Course", secondary="course_teachers", back_populates="teachers", passive_deletes="all")
    # Noter que l'association avec les sessions se fait via session_teachers (Many-to-Many)

    # Déclaration déclarative et compacte des champs liés (Style Odoo)
    max_hours_per_day = related_field("constraint_record", "max_hours_per_day", info={"label": "Max Heures par Jour", "min": 0, "max": 12, "step": "0.5"})
    max_hours_per_am = related_field("constraint_record", "max_hours_per_am", info={"label": "Max Heures par Matinée", "min": 0, "max": 8, "step": "0.5"})
    max_hours_per_pm = related_field("constraint_record", "max_hours_per_pm", info={"label": "Max Heures par Après-midi", "min": 0, "max": 8, "step": "0.5"})
    max_presence_days_per_week = related_field("constraint_record", "max_presence_days_per_week", info={"label": "Max Jours Présence par Semaine", "min": 0, "max": 6})
    max_presence_hours_per_day = related_field("constraint_record", "max_presence_hours_per_day", info={"label": "Max Heures Présence par Jour", "min": 0, "max": 12, "step": "0.5"})
    late_start_days_per_week = related_field("constraint_record", "late_start_days_per_week", info={"label": "Jours de démarrage tardif par Semaine", "min": 0, "max": 6})
    late_start_time = related_field("constraint_record", "late_start_time", info={"label": "Heure de démarrage au plus tôt", "type": "time", "placeholder": "ex: 08h30"})
    early_end_days_per_week = related_field("constraint_record", "early_end_days_per_week", info={"label": "Jours de fin précoce par Semaine", "min": 0, "max": 6})
    early_end_time = related_field("constraint_record", "early_end_time", info={"label": "Heure de fin au plus tard", "type": "time", "placeholder": "ex: 16h30"})
    min_free_days_per_week = related_field("constraint_record", "min_free_days_per_week", info={"label": "Jours libres minimum par Semaine", "min": 0, "max": 6})
    min_free_half_days_per_week = related_field("constraint_record", "min_free_half_days_per_week", info={"label": "Demi-jours libres minimum par Semaine", "min": 0, "max": 12})
    max_worked_am_per_week = related_field("constraint_record", "max_worked_am_per_week", info={"label": "Max Matinées travaillées par Semaine", "min": 0, "max": 6})
    max_worked_pm_per_week = related_field("constraint_record", "max_worked_pm_per_week", info={"label": "Max Après-midis travaillées par Semaine", "min": 0, "max": 6})
    only_one_half_day_per_day = related_field("constraint_record", "only_one_half_day_per_day", default=False, info={"label": "Ne travailler qu'une demi-journée par jour"})
    max_gap_hours_per_week = related_field("constraint_record", "max_gap_hours_per_week", default=2, info={"label": "Max heures creuses (trous) par Semaine", "min": 0, "max": 20})

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

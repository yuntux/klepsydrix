from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, Session
from backend.app.models.base import Base, related_field

class Division(Base):
    __tablename__ = "divisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False, info={"label": "Code de la classe", "placeholder": "ex: 6EME_A"})
    name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom de la classe", "placeholder": "ex: 6ème A"})
    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Nombre d'élèves", "min": 1, "max": 50})
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#CCCCCC", info={"label": "Couleur", "type": "color", "placeholder": "ex: #3498DB"})

    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    mef_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("mefs.id", ondelete="SET NULL"), nullable=True, info={"label": "Filière / MEF"})

    # Relations de navigation
    school: Mapped[Optional["School"]] = relationship("School", back_populates="divisions")
    mef: Mapped[Optional["Mef"]] = relationship("Mef", back_populates="divisions")
    partitions: Mapped[list["Partition"]] = relationship("Partition", back_populates="division", passive_deletes="all", info={"label": "Partitions"})
    courses: Mapped[list["Course"]] = relationship("Course", secondary="course_divisions", back_populates="divisions", passive_deletes="all", info={"label": "Cours"})

    # Déclaration déclarative et compacte des champs liés de contrainte (Spécifiques aux divisions)
    max_hours_per_day = related_field("constraint_record", "max_hours_per_day", info={"label": "Max Heures par Jour", "min": 0, "max": 12, "step": "0.5"})
    max_hours_per_am = related_field("constraint_record", "max_hours_per_am", info={"label": "Max Heures par Matinée", "min": 0, "max": 8, "step": "0.5"})
    max_hours_per_pm = related_field("constraint_record", "max_hours_per_pm", info={"label": "Max Heures par Après-midi", "min": 0, "max": 8, "step": "0.5"})
    late_start_days_per_week = related_field("constraint_record", "late_start_days_per_week", info={"label": "Jours de démarrage tardif par Semaine", "min": 0, "max": 6})
    late_start_time = related_field("constraint_record", "late_start_time", info={"label": "Heure de démarrage au plus tôt", "type": "time", "placeholder": "ex: 08h30"})
    early_end_days_per_week = related_field("constraint_record", "early_end_days_per_week", info={"label": "Jours de fin précoce par Semaine", "min": 0, "max": 6})
    early_end_time = related_field("constraint_record", "early_end_time", info={"label": "Heure de fin au plus tard", "type": "time", "placeholder": "ex: 16h30"})
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
            ResourceConstraint.resource_type == 'Division',
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
            ResourceConstraint.resource_type == 'Division',
            ResourceConstraint.resource_id == self.id
        ).first()
        if not constraint:
            constraint = ResourceConstraint(
                resource_type='Division',
                resource_id=self.id
            )
            constraint._via_crud_mixin_create = True
            session.add(constraint)
        return constraint

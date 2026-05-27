from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel
from backend.app.models.subject import Subject
from backend.app.models.trmd_budget import TrmdBudget
from backend.app.models.course import Course

class TrmdSynthesis(TransientModel):
    """
    Modèle virtuel (transitoire) calculé pour la synthèse TRMD.
    """
    __tablename__ = "trmd_syntheses"
    _fields = ["id", "school_id", "subject_id", "short_label", "long_label", "allocated_etp", "consumed_etp", "diff_etp", "status"]

    def __init__(self, id, school_id, subject_id, short_label, long_label, allocated_etp, consumed_etp, diff_etp, status):
        self.id = id
        self.school_id = school_id
        self.subject_id = subject_id
        self.short_label = short_label
        self.long_label = long_label
        self.allocated_etp = allocated_etp
        self.consumed_etp = consumed_etp
        self.diff_etp = diff_etp
        self.status = status

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        domain = domain or {}
        school_id = domain.get("school_id")
        if not school_id:
            return []
            
        subjects = db.query(Subject).all()
        results = []
        
        counter = 1
        for subject in subjects:
            # Trouver le budget associé à la discipline de cette matière
            budget = db.query(TrmdBudget).filter(
                TrmdBudget.school_id == school_id,
                TrmdBudget.discipline_id == subject.discipline_id
            ).first()
            
            allocated_etp = round(budget.allocated_hp / 18.0, 2) if budget else 0.0
            
            # Calculer les heures consommées par les cours de cette matière
            courses = db.query(Course).filter(
                Course.school_id == school_id,
                Course.subject_id == subject.id
            ).all()
            
            consumed_minutes = sum(c.duration_minutes for c in courses)
            consumed_hours = consumed_minutes / 60.0
            consumed_etp = round(consumed_hours / 18.0, 2)
            
            diff_etp = round(consumed_etp - allocated_etp, 2)
            
            if consumed_etp > allocated_etp:
                status = "OVER_BUDGET"
            elif consumed_etp < allocated_etp:
                status = "UNDER_BUDGET"
            else:
                status = "ON_BUDGET"
                
            results.append(cls(
                id=counter,
                school_id=school_id,
                subject_id=subject.id,
                short_label=subject.short_name,
                long_label=subject.name,
                allocated_etp=allocated_etp,
                consumed_etp=consumed_etp,
                diff_etp=diff_etp,
                status=status
            ))
            counter += 1
            
        return results

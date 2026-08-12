from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel
from backend.app.models.subject import Subject
from backend.app.models.trmd_budget import TrmdBudget
from backend.app.models.course import Course

class TrmdLine(TransientModel):
    """
    Modèle virtuel (transitoire) calculé pour la synthèse TRMD.
    """
    __tablename__ = "trmd_syntheses"
    _fields = ["id"]

    def __init__(self, id):
        self.id = id

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

            results.append(cls(
                id=counter,
            ))
            counter += 1
            
        return results

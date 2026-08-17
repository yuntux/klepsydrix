from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefGrade(Base):
    """
    Niveau de formation (ex: 6ème, 5ème, ..., Terminale) — frontière de mutualisation de
    l'effectif réduit entre Service de MEF différents (voir Service._reduced_pool_services,
    spec.md « Mutualisation de l'effectif réduit ») : deux MEF de niveaux différents ne
    mutualisent jamais, même rattachés à la même discipline ou au même Alignment.
    """
    __tablename__ = "ref_grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, info={"label": "Niveau"})

    @classmethod
    def create(cls, db: Session, vals: dict):
        """
        Cascade de création symétrique à Teacher.create() (même patron que MefService/MefDivision
        -> Service, architecture.md §15.G) : un nouveau niveau reçoit automatiquement une ligne
        TeacherGradePreference pour chaque enseignant déjà existant.
        """
        instance = super().create(db, vals)
        from backend.app.models.teacher import Teacher
        from backend.app.models.teacher_grade_preference import TeacherGradePreference
        for teacher in db.query(Teacher).all():
            TeacherGradePreference.generate_default(db, teacher, instance)
        return instance

from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy import Integer, ForeignKey
from backend.app.models.base import Base, constrains


class SpecialtyGroupConfig(Base):
    """
    Seuils de constitution des groupes de spécialité (réforme du lycée) pour un couple
    (Subject, RefGrade) — jamais par MEF : un établissement propose en général une seule offre de
    spécialités pour tous ses MEF d'un même niveau (voir wizard_specialty_group_generation.py).
    Même frontière que RefGrade.specialty_choice_limit/Service._reduced_pool_services.
    """
    __tablename__ = "specialty_group_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, info={"label": "Spécialité"})
    ref_grade_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_grades.id", ondelete="CASCADE"), nullable=False, info={"label": "Niveau"})
    max_students_per_group: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Seuil groupe (effectif max)", "min": 1, "max": 50})
    max_groups_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None, info={"label": "Nombre de groupes max.", "min": 1})

    subject: Mapped["Subject"] = relationship("Subject")
    ref_grade: Mapped["RefGrade"] = relationship("RefGrade")

    @constrains()
    def _check_subject_is_specialty(self, db: Session):
        from backend.app.models.subject import Subject
        subject = db.get(Subject, self.subject_id)
        if not subject or not subject.is_specialty:
            raise ValueError("Ce seuil doit porter sur une matière marquée « Matière de Spécialité ».")

    @constrains('max_students_per_group')
    def _check_max_students_positive(self, db: Session):
        if not self.max_students_per_group or self.max_students_per_group <= 0:
            raise ValueError("Le seuil groupe (effectif max.) doit être strictement supérieur à 0.")

    @constrains()
    def _check_unique_subject_ref_grade_pair(self, db: Session):
        duplicate = db.query(SpecialtyGroupConfig).filter(
            SpecialtyGroupConfig.subject_id == self.subject_id,
            SpecialtyGroupConfig.ref_grade_id == self.ref_grade_id,
            SpecialtyGroupConfig.id != self.id,
        ).first()
        if duplicate:
            raise ValueError("Un seuil existe déjà pour ce couple Spécialité/Niveau.")

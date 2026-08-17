"""
Préférences d'affectation d'un enseignant par niveau de formation (RefGrade) : priorité (1 = à
affecter en priorité sur ce niveau, 5 = en dernier, équivalent du couple niveaux/priorité d'EDT) et
plafond optionnel du nombre de classes distinctes de ce niveau que le professeur souhaite porter.
Une ligne par couple (teacher, ref_grade), générée automatiquement à la création de l'un ou l'autre
(voir Teacher.create()/RefGrade.create(), même patron que MefService/MefDivision -> Service,
architecture.md §15.G). Consommée par backend/app/solver/teacher_assignment.py.
"""
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy import Integer, ForeignKey, UniqueConstraint
from backend.app.models.base import Base, constrains


class TeacherGradePreference(Base):
    __tablename__ = "teacher_grade_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    ref_grade_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_grades.id", ondelete="CASCADE"), nullable=False, info={"label": "Niveau"})
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=2, info={
        "label": "Priorité", "min": 1, "max": 5,
        "help": "1 = à affecter en priorité sur ce niveau, 5 = en dernier. Plusieurs niveaux peuvent partager la même priorité.",
    })
    max_class_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={
        "label": "Nb max de classes sur ce niveau", "min": 0,
        "help": "Laisser vide pour aucun plafond.",
    })

    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="grade_preference_lines")
    ref_grade: Mapped["RefGrade"] = relationship("RefGrade")

    __table_args__ = (
        UniqueConstraint("teacher_id", "ref_grade_id", name="uq_teacher_grade_preference"),
    )

    @constrains("priority")
    def _validate_priority(self, db: Session):
        if self.priority is None or not (1 <= self.priority <= 5):
            raise ValueError("La priorité doit être comprise entre 1 et 5.")

    @constrains("max_class_count")
    def _validate_max_class_count(self, db: Session):
        if self.max_class_count is not None and self.max_class_count < 0:
            raise ValueError("Le nombre max de classes ne peut pas être négatif.")

    @classmethod
    def generate_default(cls, db: Session, teacher: "Teacher", ref_grade: "RefGrade") -> "TeacherGradePreference":
        """
        Générateur partagé, appelé par Teacher.create() (pour chaque RefGrade déjà existant) et
        RefGrade.create() (pour chaque Teacher déjà existant) — même patron que
        Service.generate_from_mef_service (architecture.md §15.G). Silencieux si la ligne existe
        déjà (couvre un appel redondant, ex: rejeu partiel d'un script) plutôt que de lever
        l'erreur d'unicité de uq_teacher_grade_preference.
        """
        existing = db.query(cls).filter(cls.teacher_id == teacher.id, cls.ref_grade_id == ref_grade.id).first()
        if existing:
            return existing
        return cls.create(db, {"teacher_id": teacher.id, "ref_grade_id": ref_grade.id, "priority": 2})

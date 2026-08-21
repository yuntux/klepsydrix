from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy import Integer, Float, ForeignKey, UniqueConstraint
from backend.app.models.base import Base, constrains


class CourseTeacherWeighting(Base):
    """
    Pondération d'un enseignant **sur un cours précis**, quand elle diffère de celle du cours.

    Pourquoi ce niveau existe, et pourquoi il est facultatif : quand un cours réunit plusieurs
    professeurs, chacun peut relever d'une pondération différente.

    La pondération est en effet une propriété du **statut de l'enseignant**, pas du cours : deux
    professeurs sur la même heure de co-enseignement peuvent légitimement être pondérés 1,1 et 1
    selon leur situation au regard de la première chaire (décret n°2014-940). `Course.
    weighting_coefficient` reste donc la valeur normale, et cette table ne porte que les
    **exceptions** — un cours simple à un seul professeur n'y a aucune ligne.

    Table d'exception plutôt que colonne sur `course_teachers` : la table d'association est un
    `Table()` nu, écrit par le mécanisme générique des collections `_ids` du CRUDMixin ; y ajouter
    une colonne métier obligerait à sortir `teacher_ids` de ce mécanisme pour toute écriture de
    cours. Une entité à part laisse `teacher_ids` intact et rend la pondération éditable comme
    n'importe quelle relation possédée.

    > STS-web, lui, **n'accepte qu'une seule pondération par service**. C'est l'audit d'export qui
    > signale l'hétérogénéité (voir sts_audit.py) plutôt que de choisir en silence laquelle
    > l'emporte.
    """
    __tablename__ = "course_teacher_weightings"
    __table_args__ = (
        UniqueConstraint("course_id", "teacher_id", name="uq_course_teacher_weighting"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, info={"label": "Cours"})
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, info={"label": "Enseignant"})
    weighting_coefficient: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, info={"label": "Pondération", "min": 0.0, "max": 5.0, "step": "0.05"})

    # Relations de navigation
    course: Mapped[Optional["Course"]] = relationship("Course", back_populates="teacher_weightings")
    teacher: Mapped[Optional["Teacher"]] = relationship("Teacher")

    @constrains("teacher_id", "course_id")
    def _check_teacher_is_on_course(self, db: Session):
        """
        Pondérer un enseignant qui n'intervient pas sur ce cours n'aurait aucun sens, et la ligne
        deviendrait invisible : `Course.weighting_for` ne la lirait jamais.
        """
        if not self.course_id or not self.teacher_id:
            return
        from backend.app.models.course import Course
        course = db.get(Course, self.course_id)
        if course and self.teacher_id not in {t.id for t in course.teachers}:
            raise ValueError(
                "Impossible de pondérer un enseignant qui n'intervient pas sur ce cours : "
                "ajoutez-le d'abord aux enseignants du cours."
            )

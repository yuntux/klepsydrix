from typing import Optional
from sqlalchemy import Table, Column, Integer, String, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import Session
from backend.app.models.gender import Gender, gender_field_info
from backend.app.models.base import Base, constrains
from backend.app.models.user import HasUserAccount

# Table de jointure Many-to-Many pour Student <-> ClassPart
student_class_parts = Table(
    "student_class_parts",
    Base.metadata,
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
    Column("class_part_id", Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), primary_key=True)
)

class Student(HasUserAccount, Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Prénom"})
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom"})
    gender: Mapped[Optional[str]] = mapped_column(Enum(Gender, name="gender_enum"), nullable=True, info=gender_field_info())
    division_id: Mapped[int] = mapped_column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False, info={"label": "Division"})
    mef_id: Mapped[int] = mapped_column(Integer, ForeignKey("mefs.id", ondelete="CASCADE"), nullable=False, info={"label": "MEF"})
    tutor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, info={"label": "Tuteur"})
    parent1_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("parents.id", ondelete="SET NULL"), nullable=True, info={"label": "Responsable légal 1"})
    parent2_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("parents.id", ondelete="SET NULL"), nullable=True, info={"label": "Responsable légal 2"})
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, unique=True, info={"label": "Compte utilisateur"})

    # Relations de navigation
    division: Mapped[Optional["Division"]] = relationship("Division", back_populates="students")
    mef: Mapped[Optional["Mef"]] = relationship("Mef")
    tutor: Mapped[Optional["Teacher"]] = relationship("Teacher", foreign_keys=[tutor_id])
    parent1: Mapped[Optional["Parent"]] = relationship("Parent", foreign_keys=[parent1_id])
    parent2: Mapped[Optional["Parent"]] = relationship("Parent", foreign_keys=[parent2_id])
    user: Mapped[Optional["User"]] = relationship("User", back_populates="student", foreign_keys=[user_id])
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", secondary=student_class_parts, back_populates="students", info={"label": "Parties de classe"})
    specialty_choices: Mapped[list["StudentSpecialtyChoice"]] = relationship(
        "StudentSpecialtyChoice", back_populates="student", passive_deletes="all", order_by="StudentSpecialtyChoice.rank",
        info={
            "label": "Vœux de spécialité",
            "widget": "many2many_ordered_list",
            "widgetParams": {
                "pickResource": "subjects",
                "pickField": "subject_id",
                "parentField": "student_id",
                "columns": [{"key": "subject_id", "label": "Spécialité", "editable": True}],
            },
        },
    )

    @constrains()
    def _check_student_mef_matches_division(self, db: Session):
        from backend.app.models.mef import MefDivision
        linked = db.query(MefDivision).filter(
            MefDivision.division_id == self.division_id,
            MefDivision.mef_id == self.mef_id
        ).first()
        if not linked:
            raise ValueError(f"Le MEF de l'élève {self.first_name} {self.last_name} doit être l'un des MEF liés à sa division.")

    @constrains()
    def _check_student_class_parts(self, db: Session):
        from backend.app.models.group import ClassPartLink
        parts = self.class_parts
        for i in range(len(parts)):
            # Cohérence de division : la division de la partie de classe doit correspondre à celle de l'élève
            if parts[i].division_id != self.division_id:
                raise ValueError(f"L'élève {self.first_name} {self.last_name} ne peut pas appartenir à la partie de classe {parts[i].name} car elle depend d'une autre division.")

            for j in range(i + 1, len(parts)):
                cp_a = parts[i]
                cp_b = parts[j]

                if cp_a.partition_id == cp_b.partition_id:
                    raise ValueError(f"L'élève {self.first_name} {self.last_name} ne peut pas appartenir à deux parties de la même partition.")

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class StudentSpecialtyChoice(Base):
    """
    Vœu de spécialité d'un élève (réforme du lycée) : une matière (Subject.is_specialty=True)
    classée par rang de préférence. Alimente le calcul des parcours et la génération des groupes
    de spécialité (voir wizard_specialty_group_generation.py). Le plafond de rangs valides pour
    un élève est celui de son niveau (RefGrade.specialty_choice_limit, via Mef.ref_grade) — un
    niveau sans plafond défini (NULL) n'est pas concerné par les spécialités.
    """
    __tablename__ = "student_specialty_choices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, info={"label": "Élève"})
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, info={"label": "Spécialité"})
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1, info={"label": "Rang", "min": 1, "max": 10})

    student: Mapped["Student"] = relationship("Student", back_populates="specialty_choices")
    subject: Mapped["Subject"] = relationship("Subject")

    @constrains()
    def _check_subject_is_specialty(self, db: Session):
        from backend.app.models.subject import Subject
        subject = db.get(Subject, self.subject_id)
        if not subject or not subject.is_specialty:
            raise ValueError("Ce vœu doit porter sur une matière marquée « Matière de Spécialité ».")

    @constrains()
    def _check_rank_within_grade_limit(self, db: Session):
        limit = self.student.mef.ref_grade.specialty_choice_limit if self.student and self.student.mef and self.student.mef.ref_grade else None
        if not limit:
            raise ValueError("Le niveau de cet élève n'est pas configuré pour les enseignements de spécialité (RefGrade.specialty_choice_limit non défini).")
        if self.rank > limit:
            raise ValueError(f"Le rang du vœu ({self.rank}) dépasse le plafond de {limit} vœux de spécialité pour ce niveau.")

    @constrains()
    def _check_unique_student_subject(self, db: Session):
        duplicate = db.query(StudentSpecialtyChoice).filter(
            StudentSpecialtyChoice.student_id == self.student_id,
            StudentSpecialtyChoice.subject_id == self.subject_id,
            StudentSpecialtyChoice.id != self.id,
        ).first()
        if duplicate:
            raise ValueError("Cet élève a déjà un vœu pour cette spécialité.")

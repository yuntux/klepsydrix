import enum
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy import Integer, String, Enum, ForeignKey, Table, Column
from backend.app.models.base import Base, constrains


student_grouping_constraint_members = Table(
    "student_grouping_constraint_members",
    Base.metadata,
    Column("constraint_id", Integer, ForeignKey("student_grouping_constraints.id", ondelete="CASCADE"), primary_key=True),
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
)


class StudentGroupingConstraintType(str, enum.Enum):
    GROUP = "group"
    SEPARATE = "separate"


STUDENT_GROUPING_CONSTRAINT_TYPE_OPTIONS = [
    {"value": StudentGroupingConstraintType.GROUP.value, "label": "À regrouper"},
    {"value": StudentGroupingConstraintType.SEPARATE.value, "label": "À séparer"},
]


class StudentGroupingConstraint(Base):
    """
    Contrainte nominative entre élèves, utilisée par le wizard d'affectation aux classes
    (Pré-rentrée, voir wizard_student_class_assignment.py) : soit un groupe d'élèves qui DOIT se
    retrouver dans la même division (GROUP — ex: jumeaux, suivi éducatif commun), soit un groupe
    qui NE DOIT PAS se retrouver ensemble (SEPARATE — ex: conflit connu entre élèves). Un seul
    modèle avec un type plutôt que deux tables symétriques : même forme, seule la sémantique
    d'application diffère côté wizard.
    """
    __tablename__ = "student_grouping_constraints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom"})
    constraint_type: Mapped[StudentGroupingConstraintType] = mapped_column(
        Enum(StudentGroupingConstraintType, name="student_grouping_constraint_type_enum"), nullable=False,
        info={"label": "Type", "type": "select", "options": STUDENT_GROUPING_CONSTRAINT_TYPE_OPTIONS},
    )
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, info={"label": "Notes"})

    students: Mapped[list["Student"]] = relationship("Student", secondary=student_grouping_constraint_members, info={"label": "Élèves"})

    @constrains()
    def _check_at_least_two_students(self, db: Session):
        if len(self.students) < 2:
            raise ValueError("Une contrainte de regroupement/séparation doit porter sur au moins deux élèves.")

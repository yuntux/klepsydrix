from typing import Optional
from sqlalchemy import Table, Column, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import Session
from backend.app.models.base import Base, constrains

# Table de jointure Many-to-Many pour Student <-> ClassPart
student_class_parts = Table(
    "student_class_parts",
    Base.metadata,
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
    Column("class_part_id", Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), primary_key=True)
)

class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Prénom"})
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom"})
    division_id: Mapped[int] = mapped_column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False, info={"label": "Division"})
    mef_id: Mapped[int] = mapped_column(Integer, ForeignKey("mefs.id", ondelete="CASCADE"), nullable=False, info={"label": "MEF"})
    tutor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, info={"label": "Tuteur"})

    # Relations de navigation
    division: Mapped[Optional["Division"]] = relationship("Division")
    mef: Mapped[Optional["Mef"]] = relationship("Mef")
    tutor: Mapped[Optional["Teacher"]] = relationship("Teacher", foreign_keys=[tutor_id])
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", secondary=student_class_parts, back_populates="students", info={"label": "Parties de classe"})

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

from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, CheckConstraint, Table
from sqlalchemy.orm import relationship, Session
from backend.app.models.base import Base, constrains

# Table de jointure Many-to-Many pour Group <-> ClassPart
group_class_parts = Table(
    "group_class_parts",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    Column("class_part_id", Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), primary_key=True)
)

class Partition(Base):
    __tablename__ = "partitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    division_id: Mapped[int] = mapped_column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False)

    # Relations de navigation
    division: Mapped[Optional["Division"]] = relationship("Division", back_populates="partitions")
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", back_populates="partition", passive_deletes="all")

class ClassPart(Base):
    __tablename__ = "class_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    division_id: Mapped[int] = mapped_column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False)
    partition_id: Mapped[int] = mapped_column(Integer, ForeignKey("partitions.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#CCCCCC")

    # Relations de navigation
    division: Mapped[Optional["Division"]] = relationship("Division", back_populates="class_parts")
    partition: Mapped[Optional["Partition"]] = relationship("Partition", back_populates="class_parts")
    groups: Mapped[list["Group"]] = relationship("Group", secondary=group_class_parts, back_populates="class_parts")

class ClassPartLink(Base):
    __tablename__ = "class_part_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    class_part_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), nullable=False)
    class_part_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), nullable=False)
    link_type: Mapped[str] = mapped_column(String(20), nullable=False) # 'CoPlaned' ou 'Excluded'
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relations de navigation
    class_part_a: Mapped[Optional["ClassPart"]] = relationship("ClassPart", foreign_keys=[class_part_a_id])
    class_part_b: Mapped[Optional["ClassPart"]] = relationship("ClassPart", foreign_keys=[class_part_b_id])

    __table_args__ = (
        UniqueConstraint("class_part_a_id", "class_part_b_id", name="uq_class_part_pair"),
        CheckConstraint("class_part_a_id < class_part_b_id", name="check_class_part_order"),
    )

    @constrains("class_part_a_id", "class_part_b_id")
    def _check_partition_overlap(self, db: Session):
        if self.class_part_a_id and self.class_part_b_id:
            cp_a = db.get(ClassPart, self.class_part_a_id)
            cp_b = db.get(ClassPart, self.class_part_b_id)
            if cp_a and cp_b and cp_a.partition_id == cp_b.partition_id:
                raise ValueError("Impossible de lier deux parties d'une même partition, elles sont disjointes par nature.")

class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False, info={"label": "Code du groupe", "placeholder": "ex: GRP_6A"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom du groupe", "placeholder": "ex: Groupe 1"})
    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Nombre d'élèves", "min": 0, "max": 100})
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#CCCCCC", info={"label": "Couleur", "type": "color", "placeholder": "ex: #F59E0B"})
    is_variable_size: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Taille variable"})

    # Relations de navigation
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", secondary=group_class_parts, back_populates="groups")
    courses: Mapped[list["Course"]] = relationship("Course", secondary="course_groups", back_populates="groups")

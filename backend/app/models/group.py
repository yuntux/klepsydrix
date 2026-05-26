from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, CheckConstraint, Table
from sqlalchemy.orm import relationship, Session
from backend.app.models.base import Base, constrains, related_field

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
    division_id: Mapped[int] = mapped_column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False, info={"readOnly": True})

    # Relations de navigation
    division: Mapped[Optional["Division"]] = relationship("Division", back_populates="partitions")
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", back_populates="partition", passive_deletes="all")

    def update(self, db: Session, vals: dict):
        if 'division_id' in vals and vals['division_id'] != self.division_id:
            raise ValueError("Il est strictement interdit de modifier la division d'une partition après sa création.")
        return super().update(db, vals)

class ClassPart(Base):
    __tablename__ = "class_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    partition_id: Mapped[int] = mapped_column(Integer, ForeignKey("partitions.id", ondelete="CASCADE"), nullable=False, info={"readOnly": True})
    division_id = related_field("partition", "division_id", info={"label": "Division", "readOnly": True})
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#CCCCCC")

    # Relations de navigation
    partition: Mapped[Optional["Partition"]] = relationship("Partition", back_populates="class_parts")
    groups: Mapped[list["Group"]] = relationship("Group", secondary=group_class_parts, back_populates="class_parts")
    students: Mapped[list["Student"]] = relationship("Student", secondary="student_class_parts", back_populates="class_parts", passive_deletes="all")

    @classmethod
    def create(cls, db: Session, vals: dict):
        instance = super().create(db, vals)
        instance._auto_generate_links(db)
        return instance

    def update(self, db: Session, vals: dict):
        if 'partition_id' in vals and vals['partition_id'] != self.partition_id:
            raise ValueError("Il est strictement interdit de modifier l'attribut 'partition_id' d'une partie de classe après sa création.")
        return super().update(db, vals)

    def _auto_generate_links(self, db: Session):
        from sqlalchemy import select
        # 1. Obtenir la partition de cette partie de classe
        partition = db.get(Partition, self.partition_id)
        if not partition:
            return
        
        division_id = partition.division_id
        
        # 2. Trouver toutes les autres partitions de la même division
        other_partitions = db.execute(
            select(Partition).filter(
                Partition.division_id == division_id,
                Partition.id != self.partition_id
            )
        ).scalars().all()
        
        if not other_partitions:
            return
            
        other_partition_ids = [p.id for p in other_partitions]
        
        # 3. Trouver toutes les parties de classe associées à ces autres partitions
        other_class_parts = db.execute(
            select(ClassPart).filter(
                ClassPart.partition_id.in_(other_partition_ids)
            )
        ).scalars().all()
        
        for other_cp in other_class_parts:
            # Assurer l'ordre des IDs pour respecter la contrainte check_class_part_order
            cp_a_id = min(self.id, other_cp.id)
            cp_b_id = max(self.id, other_cp.id)
            
            # Créer le lien automatique
            ClassPartLink.create(db, {
                "class_part_a_id": cp_a_id,
                "class_part_b_id": cp_b_id,
                "is_system_generated": True
            })


class ClassPartLink(Base):
    __tablename__ = "class_part_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    class_part_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), nullable=False)
    class_part_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), nullable=False)
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

    def update(self, db: Session, vals: dict):
        raise ValueError("Il est strictement interdit de modifier un lien entre parties de classe après sa création. Supprimez-le et recréez-le si nécessaire.")

    def delete(self, db: Session):
        from sqlalchemy import select
        from backend.app.models.student import student_class_parts
        # 1. Vérifier s'il y a des élèves communs entre les deux parties
        stmt_a = select(student_class_parts.c.student_id).filter(student_class_parts.c.class_part_id == self.class_part_a_id)
        stmt_b = select(student_class_parts.c.student_id).filter(student_class_parts.c.class_part_id == self.class_part_b_id)
        
        common_students = db.execute(
            select(student_class_parts.c.student_id)
            .filter(student_class_parts.c.student_id.in_(stmt_a))
            .filter(student_class_parts.c.student_id.in_(stmt_b))
        ).scalars().all()
        
        if common_students:
            raise ValueError("Impossible de supprimer ce lien d'incompatibilité car des élèves appartiennent simultanément aux deux parties de classe.")
            
        return super().delete(db)

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

    def get_linked_groups(self, db: Session) -> list["Group"]:
        from sqlalchemy import select, or_
        cp_ids = [cp.id for cp in self.class_parts]
        if not cp_ids:
            return []

        # Trouver tous les liens d'incompatibilité associés à ces parties de classe
        links = db.execute(
            select(ClassPartLink).filter(
                or_(
                    ClassPartLink.class_part_a_id.in_(cp_ids),
                    ClassPartLink.class_part_b_id.in_(cp_ids)
                )
            )
        ).scalars().all()

        linked_cp_ids = set()
        for l in links:
            if l.class_part_a_id in cp_ids:
                linked_cp_ids.add(l.class_part_b_id)
            if l.class_part_b_id in cp_ids:
                linked_cp_ids.add(l.class_part_a_id)

        if not linked_cp_ids:
            return []

        # Récupérer les autres groupes contenant ces parties de classe liées
        stmt_groups = select(Group).join(group_class_parts).filter(
            group_class_parts.c.class_part_id.in_(linked_cp_ids),
            Group.id != self.id
        ).distinct()

        return list(db.execute(stmt_groups).scalars().all())


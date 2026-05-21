from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, CheckConstraint, Table
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

# Table de jointure Many-to-Many pour Group <-> ClassPart
group_class_parts = Table(
    "group_class_parts",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    Column("class_part_id", Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), primary_key=True)
)

class Partition(Base):
    __tablename__ = "partitions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False)

    # Relations de navigation
    division = relationship("Division", back_populates="partitions")
    class_parts = relationship("ClassPart", back_populates="partition", passive_deletes="all")

class ClassPart(Base):
    __tablename__ = "class_parts"

    id = Column(Integer, primary_key=True, index=True)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False)
    partition_id = Column(Integer, ForeignKey("partitions.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(30), unique=True, index=True, nullable=False)
    name = Column(String(50), nullable=False)
    student_count = Column(Integer, nullable=False, default=0)
    color = Column(String(7), nullable=False, default="#CCCCCC")

    # Relations de navigation
    division = relationship("Division", back_populates="class_parts")
    partition = relationship("Partition", back_populates="class_parts")
    groups = relationship("Group", secondary=group_class_parts, back_populates="class_parts")

class ClassPartLink(Base):
    __tablename__ = "class_part_links"

    id = Column(Integer, primary_key=True, index=True)
    class_part_a_id = Column(Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), nullable=False)
    class_part_b_id = Column(Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), nullable=False)
    link_type = Column(String(20), nullable=False) # 'CoPlaned' ou 'Excluded'
    is_system_generated = Column(Boolean, nullable=False, default=True)

    # Relations de navigation
    class_part_a = relationship("ClassPart", foreign_keys=[class_part_a_id])
    class_part_b = relationship("ClassPart", foreign_keys=[class_part_b_id])

    __table_args__ = (
        UniqueConstraint("class_part_a_id", "class_part_b_id", name="uq_class_part_pair"),
        CheckConstraint("class_part_a_id < class_part_b_id", name="check_class_part_order"),
    )

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    student_count = Column(Integer, nullable=False, default=0)
    color = Column(String(7), nullable=False, default="#CCCCCC")
    is_variable_size = Column(Boolean, nullable=False, default=False)

    # Relations de navigation
    class_parts = relationship("ClassPart", secondary=group_class_parts, back_populates="groups")
    courses = relationship("Course", secondary="course_groups", back_populates="groups")

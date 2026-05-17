from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Table
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

# Tables associatives Many-to-Many pour les co-ressources et co-destinataires des séances

session_teachers = Table(
    "session_teachers",
    Base.metadata,
    Column("session_id", Integer, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("teacher_id", Integer, ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True)
)

session_classrooms = Table(
    "session_classrooms",
    Base.metadata,
    Column("session_id", Integer, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("classroom_id", Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True)
)

session_materials = Table(
    "session_materials",
    Base.metadata,
    Column("session_id", Integer, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("material_id", Integer, ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True)
)

session_divisions = Table(
    "session_divisions",
    Base.metadata,
    Column("session_id", Integer, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("division_id", Integer, ForeignKey("divisions.id", ondelete="CASCADE"), primary_key=True)
)

session_class_parts = Table(
    "session_class_parts",
    Base.metadata,
    Column("session_id", Integer, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("class_part_id", Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), primary_key=True)
)

session_groups = Table(
    "session_groups",
    Base.metadata,
    Column("session_id", Integer, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    timeslot_id = Column(Integer, ForeignKey("timeslots.id", ondelete="SET NULL"), nullable=True)
    classroom_id = Column(Integer, ForeignKey("classrooms.id", ondelete="SET NULL"), nullable=True)
    
    week_type = Column(String(1), nullable=False, default="T") # 'A', 'B', 'T'
    is_pinned = Column(Boolean, nullable=False, default=False)
    is_co_teaching = Column(Boolean, nullable=False, default=False)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)

    # Relations de navigation
    course = relationship("Course", back_populates="sessions")
    timeslot = relationship("Timeslot", back_populates="sessions")
    classroom = relationship("Classroom", back_populates="sessions")
    school = relationship("School", back_populates="sessions")

    # Co-ressources et co-destinataires Many-to-Many
    co_teachers = relationship("Teacher", secondary=session_teachers)
    co_classrooms = relationship("Classroom", secondary=session_classrooms)
    co_materials = relationship("Material", secondary=session_materials)
    co_divisions = relationship("Division", secondary=session_divisions)
    co_class_parts = relationship("ClassPart", secondary=session_class_parts)
    co_groups = relationship("Group", secondary=session_groups)

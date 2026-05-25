from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Division(Base):
    __tablename__ = "divisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False, info={"label": "Code de la classe", "placeholder": "ex: 6EME_A"})
    name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom de la classe", "placeholder": "ex: 6ème A"})
    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Nombre d'élèves", "min": 1, "max": 50})
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#CCCCCC", info={"label": "Couleur", "type": "color", "placeholder": "ex: #3498DB"})

    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    mef_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("mefs.id", ondelete="SET NULL"), nullable=True)

    # Relations de navigation
    school: Mapped[Optional["School"]] = relationship("School", back_populates="divisions")
    mef: Mapped[Optional["Mef"]] = relationship("Mef", back_populates="divisions")
    partitions: Mapped[list["Partition"]] = relationship("Partition", back_populates="division", passive_deletes="all")
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", back_populates="division", passive_deletes="all")
    courses: Mapped[list["Course"]] = relationship("Course", secondary="course_divisions", back_populates="divisions", passive_deletes="all")

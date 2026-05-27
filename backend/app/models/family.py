from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Family(Base):
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False, info={"label": "Code de la famille", "placeholder": "ex: FAM1"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom de la famille", "placeholder": "ex: Sciences"})
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False, info={"label": "Type de ressource", "placeholder": "ex: Subject"}) # 'Subject', 'Course', 'Teacher', 'Classroom'

    # Relations de navigation
    subjects: Mapped[list["Subject"]] = relationship("Subject", back_populates="family")
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="family")

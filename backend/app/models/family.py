from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Family(Base):
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False) # 'Subject', 'Course', 'Teacher', 'Classroom'

    # Relations de navigation
    subjects: Mapped[list["Subject"]] = relationship("Subject", back_populates="family")
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="family")

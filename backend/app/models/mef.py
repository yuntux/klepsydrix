from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Mef(Base):
    __tablename__ = "mefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    code_national: Mapped[str] = mapped_column(String(11), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    forecast_student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_students_per_class: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # Relations de navigation
    school: Mapped[Optional["School"]] = relationship("School")
    mef_services: Mapped[list["MefService"]] = relationship("MefService", back_populates="mef", passive_deletes="all")
    divisions: Mapped[list["Division"]] = relationship("Division", back_populates="mef")

class MefService(Base):
    __tablename__ = "mef_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mef_id: Mapped[int] = mapped_column(Integer, ForeignKey("mefs.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    weekly_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Relations de navigation
    mef: Mapped[Optional["Mef"]] = relationship("Mef", back_populates="mef_services")
    subject: Mapped[Optional["Subject"]] = relationship("Subject", back_populates="mef_services")

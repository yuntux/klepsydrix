from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Mef(Base):
    __tablename__ = "mefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    code_national: Mapped[str] = mapped_column(String(11), unique=True, index=True, nullable=False, info={"label": "Code National (MEF10)", "placeholder": "ex: 1001001211"})
    label: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Libellé", "placeholder": "ex: 6EME"})
    forecast_student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Effectif prévisionnel d'élèves", "min": 0, "max": 1000})
    max_students_per_class: Mapped[int] = mapped_column(Integer, nullable=False, default=30, info={"label": "Capacité maximale par classe", "min": 1, "max": 100})

    # Relations de navigation
    school: Mapped[Optional["School"]] = relationship("School")
    mef_services: Mapped[list["MefService"]] = relationship("MefService", back_populates="mef", passive_deletes="all")
    divisions: Mapped[list["Division"]] = relationship("Division", back_populates="mef")

class MefService(Base):
    __tablename__ = "mef_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mef_id: Mapped[int] = mapped_column(Integer, ForeignKey("mefs.id", ondelete="CASCADE"), nullable=False, info={"label": "MEF"})
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, info={"label": "Matière"})
    weekly_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, info={"label": "Volume horaire hebdomadaire", "min": 0.0, "max": 40.0, "step": "0.5"})

    # Relations de navigation
    mef: Mapped[Optional["Mef"]] = relationship("Mef", back_populates="mef_services")
    subject: Mapped[Optional["Subject"]] = relationship("Subject", back_populates="mef_services")

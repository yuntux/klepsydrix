from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base, exposed

class Mef(Base):
    __tablename__ = "mefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    code_national: Mapped[str] = mapped_column(String(11), unique=True, index=True, nullable=False, info={"label": "Code National (MEF10)", "placeholder": "ex: 1001001211"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Libellé", "placeholder": "ex: 6EME"})
    forecast_student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Effectif prévisionnel d'élèves", "min": 0, "max": 1000})
    max_students_per_class: Mapped[int] = mapped_column(Integer, nullable=False, default=30, info={"label": "Capacité maximale par classe", "min": 1, "max": 100})

    # Relations de navigation
    school: Mapped[Optional["School"]] = relationship("School")
    mef_services: Mapped[list["MefService"]] = relationship("MefService", back_populates="mef", passive_deletes="all", info={"label": "Services MEF"})
    division_links: Mapped[list["MefDivision"]] = relationship("MefDivision", back_populates="mef", passive_deletes="all", info={"label": "Classes liées"})

class MefService(Base):
    __tablename__ = "mef_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mef_id: Mapped[int] = mapped_column(Integer, ForeignKey("mefs.id", ondelete="CASCADE"), nullable=False, info={"label": "MEF"})
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, info={"label": "Matière"})
    weekly_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, info={"label": "Volume horaire hebdomadaire", "min": 0.0, "max": 40.0, "step": "0.5"})

    # Relations de navigation
    mef: Mapped[Optional["Mef"]] = relationship("Mef", back_populates="mef_services")
    subject: Mapped[Optional["Subject"]] = relationship("Subject", back_populates="mef_services")

class MefDivision(Base):
    """
    Objet de liaison entre un MEF et une Division. Porte les effectifs propres à ce
    couple : l'effectif prévu est saisi manuellement, l'effectif calculé reflète le
    nombre d'élèves réellement répartis dans la division (indépendant du MEF lié).
    """
    __tablename__ = "mef_divisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mef_id: Mapped[int] = mapped_column(Integer, ForeignKey("mefs.id", ondelete="CASCADE"), nullable=False, info={"label": "MEF"})
    division_id: Mapped[int] = mapped_column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False, info={"label": "Division"})
    forecast_student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Effectif prévu", "min": 0, "max": 50})

    # Relations de navigation
    mef: Mapped[Optional["Mef"]] = relationship("Mef", back_populates="division_links")
    division: Mapped[Optional["Division"]] = relationship("Division", back_populates="mef_links")

    @exposed
    @property
    def computed_student_count(self) -> int:
        from sqlalchemy.orm import object_session
        from backend.app.models.student import Student
        session = object_session(self)
        if not session or not self.division_id:
            return 0
        return session.query(Student).filter(
            Student.division_id == self.division_id,
            Student.mef_id == self.mef_id
        ).count()

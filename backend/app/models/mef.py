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
    """
    Gabarit réglementaire : dotation d'heures par matière pour un MEF. Sert de patron pour
    générer un Service (opérationnel) par Division associée au MEF. weekly_hours a été
    remplacé par une décomposition par type de comptage (classe entière / effectif réduit /
    effectif dédoublé), car un même volume horaire peut se répartir différemment selon ces trois
    modalités (ex: 2h30 = 2h en classe entière + 30min en effectif dédoublé).
    """
    __tablename__ = "mef_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mef_id: Mapped[int] = mapped_column(Integer, ForeignKey("mefs.id", ondelete="CASCADE"), nullable=False, info={"label": "MEF"})
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, info={"label": "Matière"})
    discipline_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("disciplines.id", ondelete="SET NULL"), nullable=True, info={"label": "Discipline"})
    election_method_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("election_methods.id", ondelete="SET NULL"), nullable=True, info={"label": "Modalité d'élection"})

    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Effectif attendu par division", "min": 0, "max": 50})
    weighting_coefficient: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, info={"label": "Pondération", "min": 0.0, "max": 5.0, "step": "0.05"})

    weekly_duration_full_class_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo classe entière (min)", "min": 0})
    weekly_duration_reduced_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo effectif réduit (min)", "min": 0})
    weekly_duration_split_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo effectif dédoublé (min)", "min": 0})
    reduced_group_student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Élèves en effectif réduit", "min": 0})

    # Relations de navigation
    mef: Mapped[Optional["Mef"]] = relationship("Mef", back_populates="mef_services")
    subject: Mapped[Optional["Subject"]] = relationship("Subject", back_populates="mef_services")
    discipline: Mapped[Optional["Discipline"]] = relationship("Discipline")
    election_method: Mapped[Optional["ElectionMethod"]] = relationship("ElectionMethod")
    services: Mapped[list["Service"]] = relationship("Service", back_populates="mef_service", info={"label": "Services générés"})

    @exposed
    @property
    def total_weekly_duration_minutes(self) -> int:
        return (self.weekly_duration_full_class_minutes or 0) \
            + (self.weekly_duration_reduced_minutes or 0) \
            + (self.weekly_duration_split_minutes or 0)

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

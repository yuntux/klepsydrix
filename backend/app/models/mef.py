from datetime import date, datetime, time
from functools import partial
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship, Session
from backend.app.models.base import Base, constrains, exposed
from backend.app.core.time_utils import get_duration_options

# Voir backend/app/models/service.py : mêmes 3 champs (miroir), même besoin d'inclure 0 ("modalité
# non utilisée", valeur par défaut) dans les options du menu déroulant.
_weekly_duration_options = partial(get_duration_options, include_zero=True)

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
    mef_services: Mapped[list["MefService"]] = relationship(
        "MefService", back_populates="mef", passive_deletes="all",
        info={
            "label": "Services MEF",
            "widget": "many2many_ordered_list",
            "widgetParams": {
                "pickResource": "subjects",
                "pickField": "subject_id",
                "parentField": "mef_id",
                "columns": [
                    {"key": "subject_id", "label": "Matière", "editable": True},
                    {"key": "discipline_id", "label": "Discipline", "resource": "disciplines", "editable": True},
                    {"key": "election_method_id", "label": "Modalité d'élection", "resource": "election_methods", "editable": True},
                    {"key": "student_count", "label": "Effectif", "editable": True},
                    {"key": "weighting_coefficient", "label": "Pondération", "editable": True},
                    {"key": "weekly_duration_full_class_minutes", "label": "Durée classe entière (min)", "editable": True},
                    {"key": "weekly_duration_reduced_minutes", "label": "Durée effectif réduit (min)", "editable": True},
                    {"key": "weekly_duration_split_minutes", "label": "Durée effectif dédoublé (min)", "editable": True},
                    {"key": "reduced_group_student_count", "label": "Élèves effectif réduit", "editable": True},
                    {"key": "total_weekly_duration_minutes", "label": "Durée totale (min)"}
                ]
            }
        }
    )
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

    weekly_duration_full_class_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo classe entière (min)", "type": "select", "options": _weekly_duration_options})
    weekly_duration_reduced_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo effectif réduit (min)", "type": "select", "options": _weekly_duration_options})
    weekly_duration_split_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo effectif dédoublé (min)", "type": "select", "options": _weekly_duration_options})
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

    @constrains('weekly_duration_full_class_minutes', 'weekly_duration_reduced_minutes', 'weekly_duration_split_minutes')
    def validate_weekly_durations_multiple(self, db: Session):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.weekly_duration_full_class_minutes, "La durée hebdomadaire classe entière du gabarit")
        validate_multiple_of_standard_timeslot(db, self.weekly_duration_reduced_minutes, "La durée hebdomadaire effectif réduit du gabarit")
        validate_multiple_of_standard_timeslot(db, self.weekly_duration_split_minutes, "La durée hebdomadaire effectif dédoublé du gabarit")

    @classmethod
    def create(cls, db, vals: dict):
        """
        À la création d'un MefService, génère automatiquement un Service pour chaque
        Division déjà liée au MEF (via MefDivision) — propagation à sens unique, en
        création seulement (voir Service.generate_from_mef_service).
        """
        instance = super().create(db, vals)
        from backend.app.models.service import Service
        mef_divisions = db.query(MefDivision).filter(MefDivision.mef_id == instance.mef_id).all()
        for mef_division in mef_divisions:
            Service.generate_from_mef_service(db, instance, mef_division)
        return instance

    def update(self, db, vals: dict):
        """
        À la modification d'un MefService, répercute les champs miroirs (voir
        Service._MEF_SERVICE_MIRROR_FIELDS) sur tous les Service déjà générés à partir de ce
        gabarit — y compris ceux ayant déjà divergé manuellement (is_synced_with_mef_service
        à False), qui perdent donc leurs ajustements locaux à chaque mise à jour du gabarit.
        Propagation forcée à chaque modification, contrairement à la création qui ne génère
        qu'une fois (voir Service.generate_from_mef_service). Reste à sens unique dans l'autre
        sens : modifier un Service n'impacte jamais son MefService d'origine.
        """
        instance = super().update(db, vals)
        from backend.app.models.service import Service
        mirror_vals = {field: getattr(self, field) for field in Service._MEF_SERVICE_MIRROR_FIELDS}
        services = db.query(Service).filter(Service.mef_service_id == self.id).all()
        for service in services:
            service.update(db, dict(mirror_vals))
        return instance

    # Pas de delete() surchargé ici : Service.mef_service_id porte ondelete="CASCADE" (décision
    # métier : un Service généré ne doit jamais survivre à la suppression de son gabarit), donc
    # CRUDMixin._cascade_delete_dependents() supprime déjà les Service liés automatiquement
    # (et transitivement leurs ServiceRepartition) — voir base.py.

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

    @classmethod
    def create(cls, db, vals: dict):
        """
        À la création d'un MefDivision (rattachement d'une classe à un MEF), génère
        automatiquement un Service pour chaque MefService déjà existant du MEF — propagation
        à sens unique, en création seulement (voir Service.generate_from_mef_service).
        """
        instance = super().create(db, vals)
        from backend.app.models.service import Service
        mef_services = db.query(MefService).filter(MefService.mef_id == instance.mef_id).all()
        for mef_service in mef_services:
            Service.generate_from_mef_service(db, mef_service, instance)
        return instance

    @property
    def display_name(self) -> str:
        mef_name = self.mef.name if self.mef else str(self.mef_id)
        division_name = self.division.name if self.division else str(self.division_id)
        return f"{mef_name} - {division_name}"

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

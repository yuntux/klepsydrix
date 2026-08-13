from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, UniqueConstraint, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from backend.app.models.base import Base, constrains, exposed

def _get_standard_duration_minutes() -> int:
    """STANDARD_TIMESLOT_DURATION dans une session dédiée — pour les contextes sans session déjà
    ouverte (callback info={"step":...}, expression SQL de Timeslot.active ci-dessous)."""
    from backend.app.core.database import SessionLocal
    from backend.app.models.system_setting import SystemSetting
    db = SessionLocal()
    try:
        return int(SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION"))
    finally:
        db.close()

def get_dynamic_step():
    return _get_standard_duration_minutes() / 60.0

class Timeslot(Base):
    __tablename__ = "timeslots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, info={"label": "Jour de la semaine", "min": 1, "max": 7}) # 1 = Lundi, 6 = Samedi
    minutes_from_midnight: Mapped[int] = mapped_column(Integer, nullable=False, info={"label": "Heure de début (minutes)", "min": 0, "max": 1440, "step": get_dynamic_step})          # ex: 480 = 8h00, 510 = 8h30

    @classmethod
    def get_noon_boundary_minutes(cls):
        """Retourne la césure (en minutes) entre le matin et l'après-midi (12h00)."""
        return 12 * 60

    # Relation avec les séances planifiées sur ce créneau

    @constrains('minutes_from_midnight')
    def _validate_hour_overflow(self, db):
        if self.minutes_from_midnight < 0:
            raise ValueError("L'heure d'un créneau ne peut pas être négative.")
            
        from backend.app.models.system_setting import SystemSetting
        val = SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION")
        duration = int(val)
        
        if self.minutes_from_midnight + duration > 24 * 60:
            raise ValueError(f"Le créneau (avec une durée de {duration}min) déborde sur la journée suivante (> 24h).")
            
        if self.minutes_from_midnight % duration != 0:
            raise ValueError(f"L'heure du créneau (minute {self.minutes_from_midnight}) n'est pas un multiple exact de la durée standard ({duration} minutes).")

    # Booléen calculé, non stocké — un créneau est "actif" quand son heure de début tombe sur un
    # multiple exact de la durée standard courante (STANDARD_TIMESLOT_DURATION, réglable en cours
    # de route). PAS de @exposed : ce champ n'a pas vocation à apparaître dans le JSON de chaque
    # ligne (ce qui ouvrirait une session DB par ligne lors d'un simple listing) — seule sa
    # filtrabilité via l'API générique est recherchée ici (?active=true), voir
    # generic.py::make_list_endpoint, architecture.md §15.U.
    #
    # .expression EST une sous-requête SQL scalaire sur system_settings, PAS un fetch Python
    # (via _get_standard_duration_minutes) : un hybrid_property.expression est un classmethod
    # sans session en paramètre, appelé au moment de CONSTRUIRE la requête, avant toute exécution
    # — une session ouverte à la main à cet instant pointerait sur la base "par défaut"
    # (core.database.SessionLocal), pas forcément celle de l'appelant (ex: la base de test isolée
    # substituée via un override FastAPI). La sous-requête, elle, s'exécute DANS la même
    # transaction/connexion que la requête englobante, quelle que soit la session utilisée par
    # l'appelant — correcte aussi bien en test qu'en production.
    @hybrid_property
    def active(self) -> bool:
        from sqlalchemy.orm import object_session
        from backend.app.models.system_setting import SystemSetting
        db = object_session(self)
        duration = (
            int(SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION"))
            if db is not None else _get_standard_duration_minutes()
        )
        return self.minutes_from_midnight % duration == 0

    @active.expression
    def active(cls):
        from sqlalchemy import cast, Integer, select as sa_select
        from backend.app.models.system_setting import SystemSetting
        duration_subquery = (
            sa_select(cast(SystemSetting.value, Integer))
            .where(SystemSetting.key == "STANDARD_TIMESLOT_DURATION")
            .scalar_subquery()
        )
        return (cls.minutes_from_midnight % duration_subquery) == 0

    @classmethod
    def get_active_timeslots(cls, db):
        return cls.read(db, domain={"active": True})


    # Index unique composé pour empêcher les doublons de créneaux
    __table_args__ = (
        UniqueConstraint("day_of_week", "minutes_from_midnight", name="uq_timeslot_day_minutes"),
    )

    def get_offset_timeslot(self, db, offset: int):
        """
        Cherche l'ID du timeslot qui a le même jour, 
        situé 'offset' crénaux plus tard.
        """
        if offset == 0:
            return self.id
        if offset < 0:
            raise ValueError("L'offset ne peut pas être négatif.")

        timeslots = db.query(Timeslot).filter(
            Timeslot.day_of_week == self.day_of_week,
            Timeslot.minutes_from_midnight > self.minutes_from_midnight
        ).order_by(Timeslot.minutes_from_midnight).limit(offset).all()

        if len(timeslots) < offset:
            raise ValueError(f"Le créneau de destination (offset +{offset}) n'existe pas ou déborde de la journée.")
            
        return timeslots[-1].id

    @exposed
    @property
    def day_of_week_str(self) -> str:
        days = {1: "Lundi", 2: "Mardi", 3: "Mercredi", 4: "Jeudi", 5: "Vendredi", 6: "Samedi", 7: "Dimanche"}
        return days.get(self.day_of_week, f"Jour {self.day_of_week}")

    @property
    def display_name(self) -> str:
        h = self.minutes_from_midnight // 60
        m = self.minutes_from_midnight % 60
        return f"{self.day_of_week_str} {h:02d}h{m:02d}"

from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, UniqueConstraint, Float
from sqlalchemy.orm import relationship
from backend.app.models.base import Base, constrains, exposed

def get_dynamic_step():
    from backend.app.core.database import SessionLocal
    from backend.app.models.system_setting import SystemSetting
    db = SessionLocal()
    try:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "STANDARD_TIMESLOT_DURATION").first()
        if not setting or not setting.value.isdigit():
            raise ValueError("Le paramètre système STANDARD_TIMESLOT_DURATION est manquant ou invalide.")
        duration = int(setting.value)
        return duration / 60.0
    finally:
        db.close()

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
        setting = db.query(SystemSetting).filter(SystemSetting.key == "STANDARD_TIMESLOT_DURATION").first()
        if not setting or not setting.value.isdigit():
            raise ValueError("Le paramètre système STANDARD_TIMESLOT_DURATION est manquant ou invalide.")
        duration = int(setting.value)
        
        if self.minutes_from_midnight + duration > 24 * 60:
            raise ValueError(f"Le créneau (avec une durée de {duration}min) déborde sur la journée suivante (> 24h).")
            
        if self.minutes_from_midnight % duration != 0:
            raise ValueError(f"L'heure du créneau (minute {self.minutes_from_midnight}) n'est pas un multiple exact de la durée standard ({duration} minutes).")

    @classmethod
    def get_active_timeslots(cls, db):
        from backend.app.models.system_setting import SystemSetting
        setting = db.query(SystemSetting).filter(SystemSetting.key == "STANDARD_TIMESLOT_DURATION").first()
        if not setting or not setting.value.isdigit():
            raise ValueError("Le paramètre système STANDARD_TIMESLOT_DURATION est manquant ou invalide.")
        duration = int(setting.value)
        
        all_ts = db.query(cls).all()
        active_ts = []
        for ts in all_ts:
            if ts.minutes_from_midnight % duration == 0:
                active_ts.append(ts)
        return active_ts


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

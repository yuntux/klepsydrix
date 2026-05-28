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
    hour: Mapped[float] = mapped_column(Float, nullable=False, info={"label": "Heure de début", "min": 0.0, "max": 24.0, "step": get_dynamic_step})          # ex: 8.0 = 8h00, 8.5 = 8h30



    # Relation avec les séances planifiées sur ce créneau

    @constrains('hour')
    def _validate_hour_overflow(self, db):
        if self.hour < 0:
            raise ValueError("L'heure d'un créneau ne peut pas être négative.")
            
        from backend.app.models.system_setting import SystemSetting
        setting = db.query(SystemSetting).filter(SystemSetting.key == "STANDARD_TIMESLOT_DURATION").first()
        if not setting or not setting.value.isdigit():
            raise ValueError("Le paramètre système STANDARD_TIMESLOT_DURATION est manquant ou invalide.")
        duration = int(setting.value)
        
        if (self.hour * 60) + duration > 24 * 60:
            raise ValueError(f"Le créneau de {self.hour}h (avec une durée de {duration}min) déborde sur la journée suivante (> 24h).")
            
        step = duration / 60.0
        if abs((self.hour / step) - round(self.hour / step)) >= 0.001:
            raise ValueError(f"L'heure du créneau ({self.hour}h) n'est pas un multiple de la durée standard ({duration} minutes).")


    @classmethod
    def get_active_timeslots(cls, db):
        from backend.app.models.system_setting import SystemSetting
        setting = db.query(SystemSetting).filter(SystemSetting.key == "STANDARD_TIMESLOT_DURATION").first()
        if not setting or not setting.value.isdigit():
            raise ValueError("Le paramètre système STANDARD_TIMESLOT_DURATION est manquant ou invalide.")
        duration = int(setting.value)
        step = duration / 60.0
        
        all_ts = db.query(cls).all()
        active_ts = []
        for ts in all_ts:
            # On considère le créneau actif s'il tombe sur un multiple exact du step
            is_active = abs((ts.hour / step) - round(ts.hour / step)) < 0.001
            if is_active:
                active_ts.append(ts)
        return active_ts

    # Index unique composé pour empêcher les doublons de créneaux
    __table_args__ = (
        UniqueConstraint("day_of_week", "hour", name="uq_timeslot_day_hour"),
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
            Timeslot.hour > self.hour
        ).order_by(Timeslot.hour).limit(offset).all()

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
        h = int(self.hour)
        m = int((self.hour - h) * 60)
        return f"{self.day_of_week_str} {h:02d}h{m:02d}"

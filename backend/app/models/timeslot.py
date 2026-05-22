from sqlalchemy import Column, Integer, UniqueConstraint, Float
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Timeslot(Base):
    __tablename__ = "timeslots"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, nullable=False) # 1 = Lundi, 6 = Samedi
    hour = Column(Float, nullable=False)          # ex: 8.0 = 8h00, 8.5 = 8h30

    # Relation avec les séances planifiées sur ce créneau


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

from sqlalchemy import Column, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Timeslot(Base):
    __tablename__ = "timeslots"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, nullable=False) # 1 = Lundi, 6 = Samedi
    hour = Column(Integer, nullable=False)        # 8 = 8h-9h, 17 = 17h-18h

    # Relation avec les séances planifiées sur ce créneau
    sessions = relationship("Session", back_populates="timeslot", passive_deletes="all")

    # Index unique composé pour empêcher les doublons de créneaux
    __table_args__ = (
        UniqueConstraint("day_of_week", "hour", name="uq_timeslot_day_hour"),
    )

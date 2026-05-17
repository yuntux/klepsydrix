from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint, Table
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

# Table de jointure Many-to-Many pour Preference <-> Period
preference_periods = Table(
    "preference_periods",
    Base.metadata,
    Column("preference_id", Integer, ForeignKey("resource_preferences.id", ondelete="CASCADE"), primary_key=True),
    Column("period_id", Integer, ForeignKey("periods.id", ondelete="CASCADE"), primary_key=True)
)

# Table de jointure Many-to-Many pour Preference <-> Alternation
preference_alternations = Table(
    "preference_alternations",
    Base.metadata,
    Column("preference_id", Integer, ForeignKey("resource_preferences.id", ondelete="CASCADE"), primary_key=True),
    Column("alternation_id", Integer, ForeignKey("alternations.id", ondelete="CASCADE"), primary_key=True)
)

class ResourcePreference(Base):
    __tablename__ = "resource_preferences"

    id = Column(Integer, primary_key=True, index=True)
    resource_type = Column(String(30), nullable=False) # 'Teacher', 'Classroom', 'Division', 'Subject', 'Group', 'Material'
    resource_id = Column(Integer, nullable=False)
    timeslot_id = Column(Integer, ForeignKey("timeslots.id", ondelete="CASCADE"), nullable=False)
    preference_level = Column(String(15), nullable=False) # 'Unsuited', 'Undesirable', 'Preferred', 'Neutral'

    # Navigation
    timeslot = relationship("Timeslot")
    periods = relationship("Period", secondary=preference_periods)
    alternations = relationship("Alternation", secondary=preference_alternations)

    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", "timeslot_id", name="uq_resource_timeslot_pref"),
    )

from typing import List
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

class ResourcePreference(Base):
    __tablename__ = "resource_preferences"

    id = Column(Integer, primary_key=True, index=True)
    resource_type = Column(String(30), nullable=False) # 'Teacher', 'Classroom', 'Division', 'Subject', 'Group', 'Material'
    resource_id = Column(Integer, nullable=False)
    timeslot_id = Column(Integer, ForeignKey("timeslots.id", ondelete="CASCADE"), nullable=False)
    preference_level = Column(String(15), nullable=False) # 'Unsuited', 'Undesirable', 'Preferred', 'Neutral'
    week_type = Column(String(1), nullable=False, default="W") # 'A', 'B', 'W'

    # Navigation
    timeslot = relationship("Timeslot")
    periods = relationship("Period", secondary=preference_periods)

    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", "timeslot_id", "week_type", name="uq_resource_timeslot_pref_week"),
    )

    @classmethod
    def create(cls, db: "Session", vals: dict):
        """
        Surcharge de create pour implémenter l'upsert et le nettoyage Neutral.
        """
        level = vals.get("preference_level")
        resource_type = vals.get("resource_type")
        resource_id = vals.get("resource_id")
        timeslot_id = vals.get("timeslot_id")
        week_type = vals.get("week_type", "W")

        if level == "Neutral" or not level:
            # Si le niveau est Neutral, on supprime l'éventuelle ligne existante
            if week_type == "W":
                # Supprimer TOUTES les préférences spécifiques (A, B et W)
                existings = db.query(cls).filter(
                    cls.resource_type == resource_type,
                    cls.resource_id == resource_id,
                    cls.timeslot_id == timeslot_id
                ).all()
                for ext in existings:
                    ext.delete(db)
            else:
                existing = db.query(cls).filter(
                    cls.resource_type == resource_type,
                    cls.resource_id == resource_id,
                    cls.timeslot_id == timeslot_id,
                    cls.week_type == week_type
                ).first()
                if existing:
                    existing.delete(db)
            return None

        # Comportement d'Upsert : si existe déjà, on appelle update à la place
        # Si on crée une contrainte 'W' (Hebdo), on supprime d'abord les anciennes contraintes spécifiques A et B pour repartir propre
        if week_type == "W":
            existings = db.query(cls).filter(
                cls.resource_type == resource_type,
                cls.resource_id == resource_id,
                cls.timeslot_id == timeslot_id,
                cls.week_type.in_(["A", "B"])
            ).all()
            for ext in existings:
                ext.delete(db)

        existing = db.query(cls).filter(
            cls.resource_type == resource_type,
            cls.resource_id == resource_id,
            cls.timeslot_id == timeslot_id,
            cls.week_type == week_type
        ).first()
        
        if existing:
            return existing.update(db, vals)

        return super().create(db, vals)

    def update(self, db: "Session", vals: dict):
        """
        Surcharge de update pour nettoyer la ligne si le niveau devient Neutral.
        """
        level = vals.get("preference_level", self.preference_level)
        if level == "Neutral" or not level:
            self.delete(db)
            return None
            
        return super().update(db, vals)



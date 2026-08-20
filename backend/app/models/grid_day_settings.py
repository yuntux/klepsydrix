"""
Heures d'ouverture de l'établissement, une ligne par jour de la semaine — voir
specs/002-yearly-timetabling-core/spec.md §0bis et architecture.md §10.D. 7 lignes fixes,
seedées par init_db.py (raw SQL, contourne create()/les
@constrains, comme le reste du seed — voir feedback_reuse_and_verify.md) : aucune ligne
supplémentaire ne peut être créée, aucune ne peut être supprimée.
"""
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy import Integer, UniqueConstraint
from backend.app.models.base import Base, constrains, exposed


def default_hour_day_end_minutes(standard_duration: int) -> int:
    """Premier créneau (multiple du pas horaire courant) supérieur ou égal à 18h — valeur par
    défaut de l'heure de fermeture d'un jour dont l'heure d'ouverture vient d'être renseignée."""
    target = 18 * 60
    remainder = target % standard_duration
    return target if remainder == 0 else target + (standard_duration - remainder)


class GridDaySettings(Base):
    __tablename__ = "grid_day_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Convention day_of_week identique à Timeslot.day_of_week (1=lundi ... 7=dimanche) — voir
    # backend/app/core/time_utils.py, seule source de vérité du libellé et de la rotation d'ordre.
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, info={
        "label": "Jour de la semaine", "min": 1, "max": 7, "readOnly": True,
    })
    hour_day_start_minutes_after_midnight: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={
        "label": "Heure d'ouverture", "widget": "timeslot_picker",
    })
    hour_day_end_minutes_after_midnight: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={
        "label": "Heure de fermeture", "widget": "timeslot_picker",
        "requiredExpr": "model.hour_day_start_minutes_after_midnight != null",
        "readOnlyExpr": "model.hour_day_start_minutes_after_midnight == null",
    })

    __table_args__ = (
        UniqueConstraint("day_of_week", name="uq_grid_day_settings_day_of_week"),
    )

    @exposed
    @property
    def display_name(self) -> str:
        from backend.app.core.time_utils import day_of_week_label
        return day_of_week_label(self.day_of_week)

    @constrains('hour_day_start_minutes_after_midnight', 'hour_day_end_minutes_after_midnight')
    def _validate_hours(self, db):
        start = self.hour_day_start_minutes_after_midnight
        end = self.hour_day_end_minutes_after_midnight

        if start is None and end is None:
            return
        if start is None:
            raise ValueError("L'heure de fermeture doit rester vide tant qu'aucune heure d'ouverture n'est saisie.")
        if end is None:
            raise ValueError("L'heure de fermeture est obligatoire dès qu'une heure d'ouverture est saisie.")

        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, start, "L'heure d'ouverture")
        validate_multiple_of_standard_timeslot(db, end, "L'heure de fermeture")

        if end <= start:
            raise ValueError("L'heure de fermeture doit être postérieure à l'heure d'ouverture.")
        if end > 23 * 60 + 59:
            raise ValueError("L'heure de fermeture ne peut pas dépasser 23h59.")

    @classmethod
    def create(cls, db: Session, vals: dict):
        raise ValueError(
            "Impossible de créer une ligne dans grid_day_settings : les 7 lignes (une par jour de "
            "la semaine) sont fixées à l'initialisation de la base."
        )

    def delete(self, db):
        raise ValueError(
            "Impossible de supprimer une ligne de grid_day_settings : les 7 lignes (une par jour "
            "de la semaine) sont permanentes."
        )

    def update(self, db, vals: dict):
        instance = super().update(db, vals)
        if 'hour_day_start_minutes_after_midnight' in vals or 'hour_day_end_minutes_after_midnight' in vals:
            from backend.app.models.timeslot import Timeslot
            Timeslot.invalidate_grid_context(db)
            Timeslot.update_timeslot_on_weekgrid_change(db, self.day_of_week)
        return instance

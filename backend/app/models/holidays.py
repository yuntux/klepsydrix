from datetime import date
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy import Integer, String, Date
from backend.app.models.base import Base, constrains


class Holidays(Base):
    """
    Période de vacances de l'établissement, bornes incluses.

    Sert exclusivement au calendrier des semaines (voir WeekCalendar) : une semaine ne peut pas
    commencer pendant des vacances, et la fin de semaine est rabotée par elles. Le solveur ne
    connaît pas cet objet — il raisonne sur une semaine type, jamais sur le calendrier réel
    (voir spec.md, « Alternances »).
    """
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Libellé", "placeholder": "ex: Vacances de la Toussaint"})
    begin_date: Mapped[date] = mapped_column(Date, nullable=False, info={"label": "Date de début"})
    end_date: Mapped[date] = mapped_column(Date, nullable=False, info={"label": "Date de fin"})

    @constrains("begin_date", "end_date")
    def _check_dates(self, db: Session):
        if self.begin_date and self.end_date and self.begin_date >= self.end_date:
            raise ValueError(
                f"La date de début des vacances « {self.name} » doit être antérieure à leur date "
                f"de fin ({self.begin_date} >= {self.end_date})."
            )

    def contains(self, jour: date) -> bool:
        """Bornes incluses : un jour égal à begin_date ou à end_date est en vacances."""
        return self.begin_date <= jour <= self.end_date

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.begin_date} → {self.end_date})"

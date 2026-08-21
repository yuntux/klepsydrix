from datetime import date, timedelta
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column, Session, object_session
from sqlalchemy import Integer, Date, Enum
from backend.app.models.base import Base, constrains, exposed
from backend.app.models.preference import WeekType


class WeekCalendar(Base):
    """
    Une semaine de l'année scolaire, étiquetée A ou B.

    C'est le pont entre le **relatif** et l'**absolu** : `Course.week_type` dit « une semaine sur
    deux » sans dire lesquelles ; cette table dit lesquelles. C'est elle qui permet de produire ce
    que STS-web attend d'une alternance : la liste explicite de ses semaines, et non une fraction
    dérivée du genre « 18/36 ».

    > Le solveur ne connaît PAS cet objet. Il raisonne sur une semaine type et sur
    > `CourseWeekType`, jamais sur le calendrier réel. `WeekCalendar` et `Alternation` ne servent
    > qu'à l'export STS et à l'affichage (voir spec.md, « Alternances »).

    `begin_date` est **unique** : une semaine donnée ne peut être ni A ni B à la fois. C'est aussi
    la clé naturelle de la table, d'où l'absence de code.
    """
    __tablename__ = "week_calendars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    begin_date: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False, info={"label": "Lundi de la semaine"})
    week_type: Mapped[Any] = mapped_column(Enum(WeekType, name="week_type_enum"), nullable=False, info={
        "label": "Type de semaine", "type": "select",
        # W n'a aucun sens ici : une semaine du calendrier est A ou B, et un cours hebdomadaire
        # se rattache aux deux. C'est l'alternance qui porte le W, pas la semaine.
        "options": [{"value": "A", "label": "Semaine A"}, {"value": "B", "label": "Semaine B"}],
    })

    @constrains("week_type")
    def _check_week_type(self, db: Session):
        if self.week_type not in (WeekType.A, WeekType.B, "A", "B"):
            raise ValueError(
                "Une semaine du calendrier est de type A ou B. Le type W (toutes les semaines) "
                "qualifie un cours ou une alternance, jamais une semaine du calendrier."
            )

    @constrains("begin_date")
    def _check_begin_date(self, db: Session):
        """
        Une semaine commence dans l'année scolaire et hors vacances. Contrainte dure : une semaine
        placée hors année ou pendant des vacances produirait une alternance fausse à l'export, et
        l'erreur ne serait visible que là-bas.
        """
        if not self.begin_date:
            return
        debut, fin = _bornes_annee(db)
        if debut and self.begin_date < debut:
            raise ValueError(
                f"La semaine du {self.begin_date} commence avant le début de l'année scolaire "
                f"({debut})."
            )
        if fin and self.begin_date > fin:
            raise ValueError(
                f"La semaine du {self.begin_date} commence après la fin de l'année scolaire ({fin})."
            )
        for vacances in _toutes_les_vacances(db):
            if vacances.contains(self.begin_date):
                raise ValueError(
                    f"La semaine du {self.begin_date} commence pendant « {vacances.name} » "
                    f"({vacances.begin_date} → {vacances.end_date})."
                )

    @exposed(info={"label": "Fin de semaine", "type": "date", "readOnly": True})
    @property
    def end_date(self) -> Optional[date]:
        """
        `begin_date + 6`, rabotée par les premières vacances rencontrées et par la fin de l'année.
        Calculée et non stockée : elle ne dépend que de données déjà en base, et déplacer une date
        de vacances doit la corriger partout sans reprise.
        """
        db = object_session(self)
        if not self.begin_date:
            return None
        fin_semaine = self.begin_date + timedelta(days=6)
        if db is None:
            return fin_semaine
        _, fin_annee = _bornes_annee(db)
        if fin_annee and fin_annee < fin_semaine:
            fin_semaine = fin_annee
        for vacances in _toutes_les_vacances(db):
            # Seules les vacances qui MORDENT sur la semaine la raccourcissent, et par leur veille.
            if self.begin_date < vacances.begin_date <= fin_semaine:
                fin_semaine = min(fin_semaine, vacances.begin_date - timedelta(days=1))
        return fin_semaine

    @property
    def display_name(self) -> str:
        return f"{self.begin_date} ({self.week_type.value if hasattr(self.week_type, 'value') else self.week_type})"


def _bornes_annee(db: Session):
    """
    Début et fin de l'année scolaire, prises sur l'établissement. Plusieurs établissements dans
    une cité scolaire : on retient l'enveloppe la plus large, le calendrier des semaines étant
    unique pour toute la base.

    Le début est **ramené au lundi de la semaine de rentrée** : une rentrée le mercredi 2
    septembre appartient à la semaine du lundi 31 août, et cette semaine-là est bien une semaine
    de l'année scolaire. Sans cette normalisation, la première semaine du calendrier serait
    refusée par sa propre contrainte. C'est aussi ce que fait CDT_6000, qui recale les dates de
    semaine reçues sur le lundi (voir FORMATS_JUSTIFICATION.md §9.8).
    """
    from backend.app.models.school import School
    ecoles = db.query(School).all()
    debuts = [s.student_start_date for s in ecoles if s.student_start_date]
    fins = [s.student_end_date for s in ecoles if s.student_end_date]
    debut = min(debuts) if debuts else None
    if debut:
        debut -= timedelta(days=debut.weekday())
    return debut, (max(fins) if fins else None)


def _toutes_les_vacances(db: Session) -> list:
    from backend.app.models.holidays import Holidays
    return db.query(Holidays).all()


def generate_week_calendar(db: Session, first_week_type: str = "A") -> int:
    """
    Engendre le calendrier des semaines de l'année : un lundi par semaine ouvrée, étiqueté A et B
    en alternance. Les semaines entièrement en vacances sont sautées **sans consommer de tour
    d'alternance** — c'est la règle usuelle, une quinzaine reprend là où elle s'était arrêtée.

    Idempotent : les semaines déjà présentes sont conservées telles quelles, seules les manquantes
    sont créées. Renvoie le nombre de semaines créées.
    """
    debut, fin = _bornes_annee(db)
    if not debut or not fin:
        raise ValueError(
            "Impossible de générer le calendrier des semaines : aucun établissement ne porte de "
            "date de rentrée et de sortie des élèves."
        )
    vacances = _toutes_les_vacances(db)
    existantes = {w.begin_date for w in db.query(WeekCalendar).all()}

    # `debut` est déjà le lundi de la semaine de rentrée (voir _bornes_annee).
    lundi = debut
    courant = first_week_type
    creees = 0
    while lundi <= fin:
        if not any(v.contains(lundi) for v in vacances):
            if lundi not in existantes:
                WeekCalendar.create(db, {"begin_date": lundi, "week_type": courant})
                creees += 1
            courant = "B" if courant == "A" else "A"
        lundi += timedelta(days=7)
    return creees

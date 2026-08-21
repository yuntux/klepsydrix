from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session, object_session
from sqlalchemy import Column, Integer, String, ForeignKey, Table, Enum
from backend.app.models.base import Base, exposed
from backend.app.models.preference import WeekType

# Périodes couvertes par l'alternance. Un cours hebdomadaire de toute l'année n'en porte aucune :
# son alternance vaut alors « toutes les semaines de l'année », sans restriction de période.
alternation_periods = Table(
    "alternation_periods",
    Base.metadata,
    Column("alternation_id", Integer, ForeignKey("alternations.id", ondelete="CASCADE"), primary_key=True),
    Column("period_id", Integer, ForeignKey("periods.id", ondelete="CASCADE"), primary_key=True),
)


class Alternation(Base):
    """
    Calendrier nommé de semaines, tel que STS-web l'attend.

    Ce n'est **pas** une fraction : un « 36/36 », « 18/36 » ou « 12/36 » n'est qu'une présentation
    dérivée du nombre de semaines. Le fichier, lui, transporte la liste explicite des lundis
    concernés (`ALTERNANCE/SEMAINES/DATE_DEBUT_SEMAINE`).

    Côté Klepsydrix, une alternance est exactement la **combinatoire du `week_type` d'un cours et
    de la liste de ses périodes** : « semaine A, au premier trimestre » désigne un ensemble de
    semaines et un seul. D'où deux champs discriminants, `week_type` et `period_ids`, et une
    collection `week_calendar_ids` qui n'est jamais saisie mais calculée à partir des deux.

    > **Le solveur ne connaît pas cet objet.** C'est un solveur annuel : il raisonne sur une
    > semaine type et sur `Course.week_type`, jamais sur des semaines calendaires. `alternation_id`
    > est un champ dérivé, calculé après coup, qui ne sert qu'à l'export STS et à l'affichage.
    """
    __tablename__ = "alternations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de l'alternance", "placeholder": "ex: A-T1"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom de l'alternance", "placeholder": "ex: Semaine A - Trimestre 1"})
    long_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, info={"label": "Libellé long"})
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, info={"label": "Couleur", "type": "color", "placeholder": "ex: #F59E0B"})
    week_type: Mapped[Any] = mapped_column(Enum(WeekType, name="week_type_enum"), nullable=False, default=WeekType.W, info={
        "label": "Type de semaine", "type": "select",
        "options": [
            {"value": "W", "label": "Toutes les semaines"},
            {"value": "A", "label": "Semaine A"},
            {"value": "B", "label": "Semaine B"},
        ],
    })

    # Relations de navigation
    periods: Mapped[list["Period"]] = relationship("Period", secondary=alternation_periods, info={"label": "Périodes"})
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="alternation", passive_deletes="all", info={"label": "Cours"})

    @exposed(info={"label": "Semaines", "resource": "week_calendars", "readOnly": True})
    @property
    def week_calendar_ids(self) -> list:
        """
        Many-to-many **calculé, non stocké** vers WeekCalendar : toutes les semaines du même
        `week_type` que l'alternance **et** intersectant au moins l'une de ses périodes.

        - `week_type` W : aucune restriction de type, les semaines A comme B sont retenues.
        - aucune période : aucune restriction de date, toute l'année est retenue.

        Non stocké parce qu'il ne dépend que de données déjà en base : ajouter une semaine au
        calendrier ou déplacer une période doit corriger toutes les alternances sans reprise.
        """
        db = object_session(self)
        if db is None:
            return []
        from backend.app.models.week_calendar import WeekCalendar

        semaines = db.query(WeekCalendar).order_by(WeekCalendar.begin_date).all()
        if self.week_type not in (WeekType.W, "W"):
            attendu = self.week_type.value if hasattr(self.week_type, "value") else self.week_type
            semaines = [
                s for s in semaines
                if (s.week_type.value if hasattr(s.week_type, "value") else s.week_type) == attendu
            ]

        periodes = list(self.periods)
        if not periodes:
            return [s.id for s in semaines]
        return [
            s.id for s in semaines
            if any(p.start_date <= (s.end_date or s.begin_date) and s.begin_date <= p.end_date for p in periodes)
        ]

    @classmethod
    def search_or_create(cls, db: Session, week_type, period_ids: list = None) -> "Alternation":
        """
        Retourne l'alternance correspondant au couple (`week_type`, ensemble de périodes), et la
        crée si elle n'existe pas encore.

        **L'ordre des périodes n'est pas discriminant** : c'est l'ensemble qui identifie
        l'alternance, d'où la comparaison sur des `set` et non sur des listes. Deux cours de même
        type de semaine couvrant les mêmes périodes dans un ordre différent partagent donc bien la
        même alternance.

        `week_type` est un `WeekType` (A/B/W) et **jamais** un `CourseWeekType.Q` : une quinzaine
        dont le côté n'est pas tranché ne désigne aucun ensemble de semaines. `Course._sync_alternation`
        s'arrête avant d'arriver ici dans ce cas ; le refus est répété pour que l'invariant soit
        énoncé et non déduit du `KeyError` qu'aurait produit le dictionnaire de libellés.
        """
        attendu = week_type.value if hasattr(week_type, "value") else (week_type or "W")
        if attendu not in ("W", "A", "B"):
            raise ValueError(
                f"Type de semaine « {attendu} » sans alternance possible : une alternance est une "
                f"liste de semaines, et une quinzaine non tranchée n'en désigne aucune."
            )
        cible = set(period_ids or [])
        for alternation in db.query(cls).all():
            actuel = alternation.week_type.value if hasattr(alternation.week_type, "value") else alternation.week_type
            if actuel == attendu and {p.id for p in alternation.periods} == cible:
                return alternation

        from backend.app.models.period import Period
        periodes = db.query(Period).filter(Period.id.in_(cible)).order_by(Period.start_date).all() if cible else []
        libelle_periodes = " + ".join(p.code for p in periodes) if periodes else "Année"
        libelle_semaine = {"W": "Toutes semaines", "A": "Semaine A", "B": "Semaine B"}[attendu]

        return cls.create(db, {
            "code": cls._free_code(db, attendu, periodes),
            "name": f"{libelle_semaine} - {libelle_periodes}",
            "long_name": f"{libelle_semaine} sur {libelle_periodes}",
            "week_type": attendu,
            "period_ids": [p.id for p in periodes],
        })

    @classmethod
    def _free_code(cls, db: Session, week_type: str, periodes: list) -> str:
        """
        Code unique par construction, comme toute colonne `code` du projet : type de semaine puis
        codes de période, dans l'ordre chronologique pour rester déterministe quel que soit l'ordre
        d'appel. Jamais suffixé — le couple (type, périodes) est déjà unique par définition, et
        `search_or_create` a déjà écarté le doublon avant d'arriver ici.
        """
        segments = [week_type] + [p.code for p in periodes]
        return "-".join(segments)[:10]

    @property
    def display_name(self) -> str:
        return self.name

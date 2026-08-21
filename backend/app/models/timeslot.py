from datetime import date, datetime, time
from typing import Optional, Any
import json
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, UniqueConstraint, Float, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from backend.app.models.base import Base, constrains, exposed

def _get_standard_duration_minutes() -> int:
    """STANDARD_TIMESLOT_DURATION dans une session dédiée — pour les contextes sans session déjà
    ouverte (callback info={"step":...}, expression SQL de Timeslot.active ci-dessous).

    MODE SYSTÈME assumé (aucun droit appliqué, voir models/base.py) : lit UN paramètre technique
    d'affichage, identique pour tout le monde, depuis un contexte qui n'a structurellement pas
    d'utilisateur courant. Aucune donnée d'établissement n'en sort."""
    from backend.app.core.database import SessionLocal
    from backend.app.models.system_setting import SystemSetting
    db = SessionLocal()
    try:
        return int(SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION"))
    finally:
        db.close()

def get_dynamic_step():
    return _get_standard_duration_minutes() / 60.0

class Timeslot(Base):
    __tablename__ = "timeslots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, info={"label": "Jour de la semaine", "min": 1, "max": 7}) # 1 = Lundi, 6 = Samedi
    minutes_from_midnight: Mapped[int] = mapped_column(Integer, nullable=False, info={"label": "Heure de début (minutes)", "min": 0, "max": 1440, "step": get_dynamic_step})          # ex: 480 = 8h00, 510 = 8h30

    @classmethod
    def get_noon_boundary_minutes(cls, db):
        """Retourne la césure (en minutes depuis minuit) entre le matin et l'après-midi — le point
        milieu ABSOLU de l'amplitude globale de la grille (heure d'ouverture la plus matinale +
        (heure de fermeture la plus tardive - heure d'ouverture la plus matinale) / 2), tous jours
        confondus (mêmes bornes que Timeslot.intraday_sequence_number). Pas la simple demi-durée :
        comparée telle quelle à un minutes_from_midnight absolu, elle placerait TOUT l'après-midi
        avant ce repère (ex: grille 8h-18h -> demi-durée seule = 5h du matin). Repli sur 12h00 tant
        qu'aucune grid_day_settings n'est configurée."""
        from backend.app.models.grid_day_settings import GridDaySettings
        min_start = db.query(func.min(GridDaySettings.hour_day_start_minutes_after_midnight)).filter(
            GridDaySettings.hour_day_start_minutes_after_midnight.isnot(None)
        ).scalar()
        max_end = db.query(func.max(GridDaySettings.hour_day_end_minutes_after_midnight)).filter(
            GridDaySettings.hour_day_end_minutes_after_midnight.isnot(None)
        ).scalar()
        if min_start is None or max_end is None:
            return 12 * 60
        return min_start + (max_end - min_start) // 2

    # Relation avec les séances planifiées sur ce créneau

    @constrains('minutes_from_midnight')
    def _validate_hour_overflow(self, db):
        if self.minutes_from_midnight < 0:
            raise ValueError("L'heure d'un créneau ne peut pas être négative.")
            
        from backend.app.models.system_setting import SystemSetting
        val = SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION")
        duration = int(val)
        
        if self.minutes_from_midnight + duration > 24 * 60:
            raise ValueError(f"Le créneau (avec une durée de {duration}min) déborde sur la journée suivante (> 24h).")
            
        if self.minutes_from_midnight % duration != 0:
            raise ValueError(f"L'heure du créneau (minute {self.minutes_from_midnight}) n'est pas un multiple exact de la durée standard ({duration} minutes).")

    # Booléen calculé, non stocké — un créneau est "actif" quand son heure de début tombe sur un
    # multiple exact de la durée standard courante (STANDARD_TIMESLOT_DURATION, réglable en cours
    # de route). PAS de @exposed : ce champ n'a pas vocation à apparaître dans le JSON de chaque
    # ligne (ce qui ouvrirait une session DB par ligne lors d'un simple listing) — seule sa
    # filtrabilité via l'API générique est recherchée ici (?active=true), voir
    # generic.py::make_list_endpoint, architecture.md §15.U.
    #
    # .expression EST une sous-requête SQL scalaire sur system_settings, PAS un fetch Python
    # (via _get_standard_duration_minutes) : un hybrid_property.expression est un classmethod
    # sans session en paramètre, appelé au moment de CONSTRUIRE la requête, avant toute exécution
    # — une session ouverte à la main à cet instant pointerait sur la base "par défaut"
    # (core.database.SessionLocal), pas forcément celle de l'appelant (ex: la base de test isolée
    # substituée via un override FastAPI). La sous-requête, elle, s'exécute DANS la même
    # transaction/connexion que la requête englobante, quelle que soit la session utilisée par
    # l'appelant — correcte aussi bien en test qu'en production.
    @hybrid_property
    def active(self) -> bool:
        from sqlalchemy.orm import object_session
        from backend.app.models.system_setting import SystemSetting
        db = object_session(self)
        duration = (
            int(SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION"))
            if db is not None else _get_standard_duration_minutes()
        )
        return self.minutes_from_midnight % duration == 0

    @active.expression
    def active(cls):
        from sqlalchemy import cast, Integer, select as sa_select
        from backend.app.models.system_setting import SystemSetting
        duration_subquery = (
            sa_select(cast(SystemSetting.value, Integer))
            .where(SystemSetting.key == "STANDARD_TIMESLOT_DURATION")
            .scalar_subquery()
        )
        return (cls.minutes_from_midnight % duration_subquery) == 0

    @classmethod
    def get_active_timeslots(cls, db):
        return cls.read(db, domain={"active": True})


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

    def count_timeslots_between(self, db, other: "Timeslot") -> int:
        """
        Inverse de get_offset_timeslot : le nombre de créneaux du même jour strictement compris
        entre self (exclu) et other (inclus) — cet offset, appliqué à self via
        get_offset_timeslot(db, offset), redonne other.id.
        """
        if other.day_of_week != self.day_of_week:
            raise ValueError("Les deux créneaux doivent être le même jour.")

        return db.query(Timeslot).filter(
            Timeslot.day_of_week == self.day_of_week,
            Timeslot.minutes_from_midnight > self.minutes_from_midnight,
            Timeslot.minutes_from_midnight <= other.minutes_from_midnight,
        ).count()

    @exposed
    @property
    def day_of_week_str(self) -> str:
        from backend.app.core.time_utils import day_of_week_label
        return day_of_week_label(self.day_of_week)

    @property
    def display_name(self) -> str:
        h = self.minutes_from_midnight // 60
        m = self.minutes_from_midnight % 60
        return f"{self.day_of_week_str} {h:02d}h{m:02d}"

    @classmethod
    def update_timeslot_on_weekgrid_change(cls, db, day_of_week: int):
        """
        Réconciliation DIFFÉRENTIELLE des Timeslot d'UN jour après modification de l'heure
        d'ouverture/fermeture de ce jour (GridDaySettings.update()) ou du pas horaire
        (voir reconcile_all_days, appelée par le wizard de paramétrage de grille quand
        STANDARD_TIMESLOT_DURATION change). Volontairement PAS un "drop tout / recrée tout" :
        - créneau conservé (même minute, dans la nouvelle amplitude ET multiple du pas courant) :
          ligne Timeslot inchangée (même id) -> les Course.timeslot_id qui la référencent restent
          posés tels quels. C'est le cas de très loin le plus fréquent (élargir une amplitude,
          diminuer le pas vers un sous-multiple du précédent) : zéro cours dépositionné.
        - créneau ajouté (nouvelle amplitude/pas) : simple insertion.
        - créneau supprimé (hors nouvelle amplitude, ou minute non multiple du nouveau pas) : les
          cours posés dessus sont dépositionnés (timeslot_id=None) puis la ligne est supprimée.
        Seul un cours "parent" (ou simple) porte un timeslot_id réel — un enfant de cours composé
        se positionne toujours par décalage depuis le timeslot de son parent (voir
        Course._sync_vals_from_parent, parent_timeslot_offset) : dépositionner le parent invalide
        donc toute la composition sans avoir à parcourir les enfants séparément.
        """
        from backend.app.models.grid_day_settings import GridDaySettings
        from backend.app.models.system_setting import SystemSetting
        from backend.app.models.course import Course

        day_settings = db.query(GridDaySettings).filter(GridDaySettings.day_of_week == day_of_week).first()
        duration = int(SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION"))

        new_minutes = set()
        if day_settings and day_settings.hour_day_start_minutes_after_midnight is not None:
            m = day_settings.hour_day_start_minutes_after_midnight
            while m < day_settings.hour_day_end_minutes_after_midnight:
                new_minutes.add(m)
                m += duration

        existing = db.query(cls).filter(cls.day_of_week == day_of_week).all()

        # 1. Créneaux disparus : dépositionner les cours posés dessus, puis supprimer la ligne.
        for ts in existing:
            if ts.minutes_from_midnight not in new_minutes:
                for c in db.query(Course).filter(Course.timeslot_id == ts.id).all():
                    c.update(db, {"timeslot_id": None})
                ts.delete(db)

        # 2. Créneaux manquants : simple insertion (le pas est déjà garanti multiple par construction).
        existing_minutes = {ts.minutes_from_midnight for ts in existing}
        for minutes in sorted(new_minutes - existing_minutes):
            cls.create(db, {"day_of_week": day_of_week, "minutes_from_midnight": minutes})

    @classmethod
    def reconcile_all_days(cls, db):
        """Réconciliation des 7 jours — utilisée quand STANDARD_TIMESLOT_DURATION change lui-même
        (contrairement à un changement d'amplitude, qui ne concerne qu'un seul jour)."""
        for day_of_week in range(1, 8):
            cls.update_timeslot_on_weekgrid_change(db, day_of_week)

    @classmethod
    def invalidate_grid_context(cls, db):
        """À appeler par tout ce qui modifie une donnée lue par _grid_context (GridDaySettings,
        STANDARD_TIMESLOT_DURATION, PUBLIC_DISPLAY_HOURS_BY_SEQUENCE) — le cache est posé sur `db`
        pour la durée d'une requête (voir architecture.md §15.V) et doit être invalidé dès que ce
        qu'il mémorise change en cours de route, sinon une lecture ultérieure dans la même requête
        (ex: la réponse du wizard de paramétrage de grille, qui modifie puis sérialise) verrait un
        état obsolète."""
        db._grid_context_cache = None

    def _grid_context(self, db):
        """Contexte ambiant posé sur `db` (idiome try/finally direct, voir architecture.md §15.V) :
        mémorise, pour la durée d'un listing, le pas horaire et l'heure d'ouverture la plus
        matinale (toutes GridDaySettings confondues) — évite une requête SQL par ligne pour
        intraday_sequence_number/public_display_* (même piège que Timeslot.active, voir plus haut)."""
        if getattr(db, "_grid_context_cache", None) is None:
            from backend.app.models.grid_day_settings import GridDaySettings
            from backend.app.models.system_setting import SystemSetting
            duration = int(SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION"))
            min_start = db.query(func.min(GridDaySettings.hour_day_start_minutes_after_midnight)).filter(
                GridDaySettings.hour_day_start_minutes_after_midnight.isnot(None)
            ).scalar()
            raw_display = SystemSetting.get_system_setting_value(db, "PUBLIC_DISPLAY_HOURS_BY_SEQUENCE")
            display_by_sequence = json.loads(raw_display) if raw_display else {}
            db._grid_context_cache = (duration, min_start, display_by_sequence)
        return db._grid_context_cache

    @exposed
    @property
    def intraday_sequence_number(self) -> Optional[int]:
        """Numéro de séquence DANS LA JOURNÉE (1 = premier créneau du jour dont l'heure d'ouverture
        est la plus matinale, tous jours confondus) — pour un jour ouvrant plus tard que les
        autres, le premier créneau du jour n'est donc pas forcément la séquence 1 (ex: un jour
        ouvert uniquement l'après-midi commence à une séquence > 1)."""
        from sqlalchemy.orm import object_session
        db = object_session(self)
        if db is None:
            return None
        _duration, min_start, _display = self._grid_context(db)
        if min_start is None:
            return None
        duration = int(_duration)
        return (self.minutes_from_midnight - min_start) // duration + 1

    @exposed
    @property
    def public_display_start_minutes_after_midnight(self) -> Optional[int]:
        """Heure de début affichée au public pour ce numéro de séquence (PUBLIC_DISPLAY_HOURS_BY_
        SEQUENCE) — repli sur l'heure réelle du créneau UNIQUEMENT si la séquence n'a AUCUNE
        entrée dans ce réglage (grille élargie depuis la dernière saisie). Si l'entrée existe mais
        que sa valeur de début est `null`, c'est une valeur VOULUE (ne pas afficher cette heure-là,
        ex: init_db.py seed `[null, fin]` sur les séquences paires) — retourne `None` telle quelle,
        pas de repli sur l'heure réelle dans ce cas."""
        from sqlalchemy.orm import object_session
        db = object_session(self)
        seq = self.intraday_sequence_number if db is not None else None
        if db is not None and seq is not None:
            _duration, _min_start, display_by_sequence = self._grid_context(db)
            entry = display_by_sequence.get(str(seq))
            if entry:
                return entry[0]
        return self.minutes_from_midnight

    @exposed
    @property
    def public_display_end_minutes_after_midnight(self) -> Optional[int]:
        """Symétrique de public_display_start_minutes_after_midnight (même règle : repli sur la
        fin réelle — minutes_from_midnight + pas horaire courant — uniquement si l'entrée est
        absente ; une valeur de fin explicitement `null` reste `None`, voir sa docstring)."""
        from sqlalchemy.orm import object_session
        db = object_session(self)
        seq = self.intraday_sequence_number if db is not None else None
        if db is not None and seq is not None:
            duration, _min_start, display_by_sequence = self._grid_context(db)
            entry = display_by_sequence.get(str(seq))
            if entry:
                return entry[1]
        else:
            duration = _get_standard_duration_minutes()
        return self.minutes_from_midnight + int(duration)

from datetime import date, datetime, time
from typing import Optional, Any
import enum
import json
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, String, Text, Integer, Enum, func
from backend.app.models.base import Base
from backend.app.core.time_utils import day_of_week_label

class SystemSettingKey(str, enum.Enum):
    STANDARD_TIMESLOT_DURATION = "STANDARD_TIMESLOT_DURATION"
    FIRST_DAY_OF_THE_WEEK = "FIRST_DAY_OF_THE_WEEK"
    HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT = "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT"
    HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT = "HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT"
    PUBLIC_DISPLAY_HOURS_BY_SEQUENCE = "PUBLIC_DISPLAY_HOURS_BY_SEQUENCE"
    DIVISION_PART_NAME_HAS_DIV_CODE = "DIVISION_PART_NAME_HAS_DIV_CODE"
    DIVISION_PART_NAME_HAS_SUBJECT_CODE = "DIVISION_PART_NAME_HAS_SUBJECT_CODE"
    DIVISION_PART_NAME_SEPARATOR = "DIVISION_PART_NAME_SEPARATOR"
    DIVISION_PART_NAME_NUMBER_FORMAT = "DIVISION_PART_NAME_NUMBER_FORMAT"
    GROUP_NAME_HAS_DIV_CODE = "GROUP_NAME_HAS_DIV_CODE"
    GROUP_NAME_HAS_SUBJECT_CODE = "GROUP_NAME_HAS_SUBJECT_CODE"
    GROUP_NAME_SEPARATOR = "GROUP_NAME_SEPARATOR"
    GROUP_NAME_NUMBER_FORMAT = "GROUP_NAME_NUMBER_FORMAT"
    MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT = "MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT"

SETTING_LABELS = {
    SystemSettingKey.STANDARD_TIMESLOT_DURATION: "[Grille horaire] : durée minimale d'un créneau (en minutes)",
    SystemSettingKey.FIRST_DAY_OF_THE_WEEK: "[Grille horaire] : premier jour de la semaine",
    SystemSettingKey.HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT: "[Grille horaire] : heure de début de la récréation du matin",
    SystemSettingKey.HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT: "[Grille horaire] : heure de début de la récréation de l'après-midi",
    SystemSettingKey.PUBLIC_DISPLAY_HOURS_BY_SEQUENCE: "[Grille horaire] : horaires affichés par numéro de séquence",
    SystemSettingKey.DIVISION_PART_NAME_HAS_DIV_CODE: "[Nommage parties de classe] : intégrer le code classe",
    SystemSettingKey.DIVISION_PART_NAME_HAS_SUBJECT_CODE: "[Nommage parties de classe] : intégrer le code matière",
    SystemSettingKey.DIVISION_PART_NAME_SEPARATOR: "[Nommage parties de classe] : séparateur",
    SystemSettingKey.DIVISION_PART_NAME_NUMBER_FORMAT: "[Nommage parties de classe] : type numérotation",
    SystemSettingKey.GROUP_NAME_HAS_DIV_CODE: "[Nommage groupe] : intégrer la première lettre du code classe",
    SystemSettingKey.GROUP_NAME_HAS_SUBJECT_CODE: "[Nommage groupe] : intégrer le code matière",
    SystemSettingKey.GROUP_NAME_SEPARATOR: "[Nommage groupe] : séparateur",
    SystemSettingKey.GROUP_NAME_NUMBER_FORMAT: "[Nommage groupe] : type numérotation",
    SystemSettingKey.MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT: "Mutualiser les groupes à effectif réduit même sans alignement formel",
}

# Options de la liste déroulante FIRST_DAY_OF_THE_WEEK — 1=lundi ... 7=dimanche, même convention
# que Timeslot.day_of_week (voir time_utils.day_of_week_label, seule source de vérité du libellé).
FIRST_DAY_OF_THE_WEEK_OPTIONS = [{"value": str(d), "label": day_of_week_label(d)} for d in range(1, 8)]

# Valeurs autorisées pour les paramètres de type "liste déroulante" (*_NUMBER_FORMAT)
NUMBER_FORMAT_ALPHABETIC = "alphabetique"
NUMBER_FORMAT_NUMERIC = "numerique"
NUMBER_FORMAT_CHOICES = [NUMBER_FORMAT_ALPHABETIC, NUMBER_FORMAT_NUMERIC]

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[Any] = mapped_column(Enum(SystemSettingKey, native_enum=False), index=True, unique=True, nullable=False, info={
        "label": "Paramètre système", 
        "type": "select",
        "options": [
            {"value": k.value, "label": SETTING_LABELS.get(k, k.value)}
            for k in SystemSettingKey
        ]
    })
    value: Mapped[str] = mapped_column(Text, nullable=False, info={
        "label": "Valeur", "placeholder": "ex: 30", "widget": "system_setting_value",
        # Requis uniquement pour les paramètres qui doivent toujours porter une valeur exploitable
        # (voir architecture.md §15.F.bis) — un seul champ `value` partagé par toutes les clés, donc
        # une expression PAR LIGNE plutôt qu'un `required` statique qui s'appliquerait à toutes.
        "requiredExpr": "['STANDARD_TIMESLOT_DURATION', 'FIRST_DAY_OF_THE_WEEK'].includes(model.key)",
        # PUBLIC_DISPLAY_HOURS_BY_SEQUENCE est un JSON généré par wizard_grid_settings.rpc_apply
        # (voir _render_display_rows) : jamais éditable à la main depuis la vue générique
        # "Paramètres système", uniquement via le wizard « Grille horaire ». Restriction UI
        # (readOnlyExpr, comme toute colonne — voir architecture.md §15.E) : l'API générique reste
        # fonctionnelle pour l'admin/les scripts, seule l'IHM guide vers le bon flux.
        "readOnlyExpr": "model.key === 'PUBLIC_DISPLAY_HOURS_BY_SEQUENCE'",
    })

    @classmethod
    def get_system_setting_value(cls, db, key: str) -> str:
        setting = db.query(cls).filter(cls.key == key).first()
        if key == "STANDARD_TIMESLOT_DURATION":
            if not setting or not setting.value or not setting.value.isdigit():
                raise ValueError("Le paramètre système STANDARD_TIMESLOT_DURATION est manquant ou invalide.")
        return setting.value if setting else None

    def delete(self, db):
        if self.key == SystemSettingKey.STANDARD_TIMESLOT_DURATION:
            raise ValueError("Il est impossible de supprimer le paramètre système 'STANDARD_TIMESLOT_DURATION'.")
        return super().delete(db)

    @classmethod
    def _validate_value_for_key(cls, db, key, value, bypass_grid_checks: bool = False):
        """Validation par clé, partagée entre create() et update() (toutes deux peuvent être le
        premier point d'écriture d'un réglage sans valeur par défaut, ex: les horaires de
        récréation). `bypass_grid_checks` : voir GridDaySettings/wizard_grid_settings — le wizard
        de paramétrage de grille applique pas -> jours -> récréations dans une seule transaction et
        assume les dépositionnements induits ; il désactive donc ces vérifications croisées
        (déjà refaites par ses propres étapes) plutôt que de se heurter à un état intermédiaire
        transitoirement incohérent."""
        key = key.value if hasattr(key, "value") else key
        if key == SystemSettingKey.FIRST_DAY_OF_THE_WEEK.value:
            if not str(value).isdigit() or not (1 <= int(value) <= 7):
                raise ValueError("Le premier jour de la semaine doit être un entier compris entre 1 (lundi) et 7 (dimanche).")
        elif key in (
            SystemSettingKey.HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT.value,
            SystemSettingKey.HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT.value,
        ) and not bypass_grid_checks:
            cls._validate_break_start(db, key, value)

    @classmethod
    def _validate_break_start(cls, db, key: str, value):
        if value is None or str(value) == "":
            return
        if not str(value).isdigit():
            raise ValueError("L'heure de début d'une récréation doit être un nombre de minutes après minuit.")
        minutes = int(value)

        from backend.app.models.timeslot import Timeslot
        from backend.app.models.grid_day_settings import GridDaySettings
        duration = int(cls.get_system_setting_value(db, SystemSettingKey.STANDARD_TIMESLOT_DURATION.value))
        min_start = db.query(func.min(GridDaySettings.hour_day_start_minutes_after_midnight)).filter(
            GridDaySettings.hour_day_start_minutes_after_midnight.isnot(None)
        ).scalar()
        max_end = db.query(func.max(GridDaySettings.hour_day_end_minutes_after_midnight)).filter(
            GridDaySettings.hour_day_end_minutes_after_midnight.isnot(None)
        ).scalar()
        if min_start is None or max_end is None:
            raise ValueError("Impossible de définir une récréation tant qu'aucune heure d'ouverture n'est saisie sur la grille horaire.")

        if minutes % duration != 0:
            raise ValueError(f"L'heure de la récréation doit être un multiple exact du pas horaire ({duration} min).")
        if minutes >= max_end:
            raise ValueError("L'heure de la récréation doit être antérieure à l'heure de fermeture la plus tardive de la grille.")

        if key == SystemSettingKey.HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT.value:
            if minutes < min_start + duration:
                raise ValueError("La récréation du matin doit commencer au moins un pas horaire après l'heure d'ouverture la plus matinale de la grille.")
            afternoon = cls.get_system_setting_value(db, SystemSettingKey.HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT.value)
            if afternoon and afternoon.isdigit() and minutes >= int(afternoon):
                raise ValueError("La récréation du matin doit être strictement antérieure à la récréation de l'après-midi.")
        else:
            morning = cls.get_system_setting_value(db, SystemSettingKey.HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT.value)
            lower_bound = max(min_start, int(morning)) if morning and morning.isdigit() else min_start
            if minutes < lower_bound + duration:
                raise ValueError("La récréation de l'après-midi doit commencer au moins un pas horaire après l'heure d'ouverture la plus matinale et après la récréation du matin.")

    # Clés dont un changement invalide le cache ambiant de Timeslot._grid_context (voir
    # architecture.md §15.V) — pas horaire et horaires publics affichés par séquence.
    _GRID_CONTEXT_KEYS = (
        SystemSettingKey.STANDARD_TIMESLOT_DURATION.value,
        SystemSettingKey.PUBLIC_DISPLAY_HOURS_BY_SEQUENCE.value,
    )

    @classmethod
    def create(cls, db, vals: dict, bypass_grid_checks: bool = False):
        if vals.get("key") is not None and vals.get("value") is not None:
            cls._validate_value_for_key(db, vals["key"], vals["value"], bypass_grid_checks=bypass_grid_checks)
        instance = super().create(db, vals)
        key = vals.get("key")
        if (key.value if hasattr(key, "value") else key) in cls._GRID_CONTEXT_KEYS:
            from backend.app.models.timeslot import Timeslot
            Timeslot.invalidate_grid_context(db)
        return instance

    def update(self, db, vals: dict, bypass_grid_checks: bool = False):
        if 'value' in vals and str(vals['value']) != str(self.value):
            self._validate_value_for_key(db, self.key, vals['value'], bypass_grid_checks=bypass_grid_checks)
            if self.key.value in self._GRID_CONTEXT_KEYS:
                from backend.app.models.timeslot import Timeslot
                Timeslot.invalidate_grid_context(db)

        if self.key == SystemSettingKey.STANDARD_TIMESLOT_DURATION and 'value' in vals and str(vals['value']) != str(self.value):
            from backend.app.core.time_utils import STANDARD_TIMESLOT_DURATION_MIN_MINUTES, STANDARD_TIMESLOT_DURATION_MAX_MINUTES
            new_val = str(vals['value'])
            if not new_val.isdigit() or not (STANDARD_TIMESLOT_DURATION_MIN_MINUTES <= int(new_val) <= STANDARD_TIMESLOT_DURATION_MAX_MINUTES):
                raise ValueError(
                    f"La durée standard d'un créneau doit être un entier compris entre "
                    f"{STANDARD_TIMESLOT_DURATION_MIN_MINUTES} et {STANDARD_TIMESLOT_DURATION_MAX_MINUTES} minutes."
                )

            old_duration = int(self.value) if self.value.isdigit() else 30
            new_duration = int(new_val)

            from backend.app.models.course import Course

            # 1. Si on augmente la durée, on vérifie d'abord qu'aucun cours n'est placé sur un créneau qui deviendrait hors-grille
            #    (sauté si le wizard de grille assume déjà les dépositionnements induits — voir bypass_grid_checks)
            if new_duration > old_duration and not bypass_grid_checks:
                from backend.app.models.timeslot import Timeslot
                from backend.app.core.time_utils import minutes_to_hours
                # On inspecte les cours qui ont un timeslot assigné
                for c in db.query(Course).join(Timeslot).filter(Course.timeslot_id != None).all():
                    if c.timeslot.minutes_from_midnight % new_duration != 0:
                        _, hour_text = minutes_to_hours(c.timeslot.minutes_from_midnight)
                        raise ValueError(
                            f"Modification interdite : le cours (ID {c.id}) est positionné sur un créneau "
                            f"({hour_text}) qui n'est pas un multiple de {new_duration} minutes."
                        )

            # 2. Ensuite, on vérifie et on recalcule les offsets relatifs des cours enfants
            courses_with_offset = db.query(Course).filter(Course.parent_timeslot_offset > 0).all()
            for course in courses_with_offset:
                offset_minutes = course.parent_timeslot_offset * old_duration
                if offset_minutes % new_duration != 0:
                    if bypass_grid_checks:
                        continue
                    raise ValueError(
                        f"Modification interdite : le cours complexe (ID {course.id}) a un décalage de "
                        f"{offset_minutes} minutes, ce qui n'est pas un multiple de la nouvelle durée ({new_duration}m)."
                    )
                course.parent_timeslot_offset = offset_minutes // new_duration

        return super().update(db, vals)

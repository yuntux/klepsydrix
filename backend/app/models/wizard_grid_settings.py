"""
Wizard « Grille horaire » (menu Paramètres) — 6 étapes (premier jour + pas horaire / heures
d'ouverture par jour / récréations / aperçu des horaires publics / confirmation avec impact
chiffré / résultat), même patron TransientModel + __actions__ que les autres wizards (voir
wizard_specialty_group_generation.py). Rien n'est écrit en base avant la confirmation de la
dernière étape utile (rpc_apply) — les étapes 1 à 4 ne font que calculer des aperçus, jamais de
création/modification réelle (voir architecture.md, nouvelle sous-section « Grille horaire »).
"""
import json
import math
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel, requires_access
from backend.app.core.time_utils import day_of_week_label, day_of_week_sort_key
from backend.app.core.time_utils import get_standard_timeslot_duration_options

# Options à valeur ENTIÈRE (contrairement à SystemSetting.FIRST_DAY_OF_THE_WEEK_OPTIONS, à valeur
# texte car SystemSetting.value est une colonne string) : le champ du wizard, lui, est un int Python
# natif (voir __init__/rpc_load_day_rows), donc ses options doivent l'être aussi.
_FIRST_DAY_OF_THE_WEEK_OPTIONS = [{"value": d, "label": day_of_week_label(d)} for d in range(1, 8)]


def _render_day_rows(db: Session, first_day_of_week: int) -> list[dict]:
    """Lignes d'heures d'ouverture éditées par le wizard — reflète l'état RÉELLEMENT persisté de
    grid_day_settings (l'étape 2 part de là, pas d'une grille vierge)."""
    from backend.app.models.grid_day_settings import GridDaySettings
    rows = sorted(
        db.query(GridDaySettings).all(),
        key=lambda d: day_of_week_sort_key(d.day_of_week, first_day_of_week),
    )
    return [
        {
            "id": d.day_of_week,
            "day_of_week": d.day_of_week,
            "display_name": day_of_week_label(d.day_of_week),
            "hour_day_start_minutes_after_midnight": d.hour_day_start_minutes_after_midnight,
            "hour_day_end_minutes_after_midnight": d.hour_day_end_minutes_after_midnight,
        }
        for d in rows
    ]


def _display_bounds(anchor: int, duration: int) -> tuple[int, int]:
    """Bornes ENTIÈRES les plus proches qui restent strictement à l'intérieur de l'intervalle
    ouvert (ancre - pas/2, ancre + pas/2) — formule valable même si le pas horaire est impair
    (demi-pas fractionnaire, ex: 15 min -> 7.5). Calculée ICI (côté serveur) : ClockTimeField.vue
    ne fait que LIRE les deux valeurs qui en résultent (widgetParams.{minField, maxField}), il
    n'a aucune connaissance de créneau/pas horaire — un widget générique borné par deux champs
    d'une même ligne, réutilisable en dehors de toute grille horaire."""
    half = duration / 2
    return math.floor(anchor - half) + 1, math.ceil(anchor + half) - 1


def _render_display_rows(day_rows: list[dict], duration: int, existing_display_map: dict) -> list[dict]:
    """Aperçu des horaires publics par séquence — voir spec.md « Grille horaire » pour
    l'algorithme exact. Repli sur l'heure réelle (début_min + i*pas) quand une séquence n'a pas
    encore d'entrée dans PUBLIC_DISPLAY_HOURS_BY_SEQUENCE."""
    starts = [r["hour_day_start_minutes_after_midnight"] for r in day_rows if r.get("hour_day_start_minutes_after_midnight") is not None]
    ends = [r["hour_day_end_minutes_after_midnight"] for r in day_rows if r.get("hour_day_end_minutes_after_midnight") is not None]
    if not starts or not ends:
        return []
    start_min = min(starts)
    end_max = max(ends)
    sequence_count = (end_max - start_min) // duration

    rows = []
    for i in range(sequence_count):
        seq = i + 1
        minute = start_min + i * duration
        real_start, real_end = minute, minute + duration
        entry = existing_display_map.get(str(seq))
        start_min_bound, start_max_bound = _display_bounds(real_start, duration)
        end_min_bound, end_max_bound = _display_bounds(real_end, duration)
        rows.append({
            "id": seq,
            "sequence_number": seq,
            # Repli sur l'heure réelle UNIQUEMENT si l'entrée entière est absente pour cette
            # séquence — même règle que Timeslot.public_display_start/end_minutes_after_midnight.
            # Une entrée existante avec une valeur `null` (ex: [début, null] ou [null, fin], voir
            # init_db.py sur les séquences impaires/paires) est une valeur VOULUE (ne pas afficher
            # cette heure-là) : elle reste `None` ici, pas de repli — l'aperçu du wizard doit
            # montrer exactement ce que la grille affichera une fois appliqué.
            "public_display_start_minutes_after_midnight": entry[0] if entry else real_start,
            "public_display_end_minutes_after_midnight": entry[1] if entry else real_end,
            # Bornes min/max déjà calculées, jamais montrées en colonne (voir
            # _DISPLAY_ROWS_WIDGET_PARAMS) : ClockTimeField.vue les lit telles quelles sur la ligne.
            # Fenêtres disjointes (adjacentes au point milieu) -> le début public reste
            # structurellement toujours antérieur à la fin publique, sans contrôle croisé dédié.
            "start_display_min_minutes_after_midnight": start_min_bound,
            "start_display_max_minutes_after_midnight": start_max_bound,
            "end_display_min_minutes_after_midnight": end_min_bound,
            "end_display_max_minutes_after_midnight": end_max_bound,
        })
    return rows


def _compute_impacted_course_count(db: Session, day_rows: list[dict], duration: int) -> int:
    """Dry-run en lecture seule de la réconciliation différentielle (voir
    Timeslot.update_timeslot_on_weekgrid_change, même logique de créneaux « supprimés ») — pour
    que l'aperçu chiffré de l'étape de confirmation et l'application réelle restent rigoureusement
    cohérents, sans jamais écrire en base ici."""
    from backend.app.models.timeslot import Timeslot
    from backend.app.models.course import Course

    total = 0
    for row in day_rows:
        new_minutes = set()
        start = row.get("hour_day_start_minutes_after_midnight")
        end = row.get("hour_day_end_minutes_after_midnight")
        if start is not None and end is not None:
            m = start
            while m < end:
                new_minutes.add(m)
                m += duration

        existing = db.query(Timeslot).filter(Timeslot.day_of_week == row["day_of_week"]).all()
        removed_ids = [ts.id for ts in existing if ts.minutes_from_midnight not in new_minutes]
        if removed_ids:
            total += db.query(Course).filter(Course.timeslot_id.in_(removed_ids)).count()
    return total


_DAY_ROWS_WIDGET_PARAMS = {
    "columns": [
        {"key": "display_name", "label": "Jour", "width": 120},
        {"key": "hour_day_start_minutes_after_midnight", "label": "Heure d'ouverture", "width": 160, "widget": "timeslot_picker", "widgetParams": {"includeEmpty": True}},
        {"key": "hour_day_end_minutes_after_midnight", "label": "Heure de fermeture", "width": 160, "widget": "timeslot_picker", "widgetParams": {"includeEmpty": True}, "readOnlyExpr": "model.hour_day_start_minutes_after_midnight == null"},
    ],
    "listConfig": {"editableInline": True, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
}

_DISPLAY_ROWS_WIDGET_PARAMS = {
    "columns": [
        {"key": "sequence_number", "label": "Séquence", "width": 100, "readOnly": True},
        # Bornes déjà calculées côté serveur (_display_bounds, dans _render_display_rows) et
        # simplement lues par ClockTimeField.vue (widgetParams.{minField, maxField}) — le widget
        # lui-même ne connaît ni créneau ni pas horaire. Les 4 champs *_display_min/max_...
        # n'apparaissent nulle part dans ce tableau `columns` (list_preview ne rend que les
        # colonnes explicitement déclarées) : disponibles sur la ligne, jamais affichés.
        {"key": "public_display_start_minutes_after_midnight", "label": "Début public", "width": 140, "widget": "clock_time", "widgetParams": {"minField": "start_display_min_minutes_after_midnight", "maxField": "start_display_max_minutes_after_midnight"}},
        {"key": "public_display_end_minutes_after_midnight", "label": "Fin publique", "width": 140, "widget": "clock_time", "widgetParams": {"minField": "end_display_min_minutes_after_midnight", "maxField": "end_display_max_minutes_after_midnight"}},
    ],
    "listConfig": {"editableInline": True, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
}


class WizardGridSettings(TransientModel):
    """Enregistrement singleton (id=1 fixe, pas de liste), voir ui.json."""
    __tablename__ = "wizard_grid_settings"
    _fields = [
        "id", "intro_html",
        "first_day_of_week", "standard_timeslot_duration",
        "day_rows",
        "morning_break_start_minutes_after_midnight", "afternoon_break_start_minutes_after_midnight",
        "display_rows",
        "confirm_html",
        "result_html",
    ]
    _field_info = {
        "intro_html": {"type": "html", "label": " ", "readOnly": True},
        "first_day_of_week": {"label": "Premier jour de la semaine", "type": "select", "options": _FIRST_DAY_OF_THE_WEEK_OPTIONS},
        "standard_timeslot_duration": {"label": "Pas horaire (minutes)", "type": "select", "options": get_standard_timeslot_duration_options()},
        "day_rows": {"label": "Heures d'ouverture", "type": "text", "widget": "list_preview", "readOnly": True},
        "morning_break_start_minutes_after_midnight": {"label": "Récréation du matin", "type": "select", "widget": "timeslot_picker", "widgetParams": {"includeEmpty": True}},
        "afternoon_break_start_minutes_after_midnight": {"label": "Récréation de l'après-midi", "type": "select", "widget": "timeslot_picker", "widgetParams": {"includeEmpty": True}},
        "display_rows": {"label": "Horaires affichés", "type": "text", "widget": "list_preview", "readOnly": True},
        "confirm_html": {"type": "html", "label": " ", "readOnly": True},
        "result_html": {"type": "html", "label": " ", "readOnly": True},
    }
    __actions__ = [{
        "id": "configure_grid",
        "label": "Grille horaire",
        "type": "wizard",
        "steps": [
            {
                "id": "basics",
                "title": "1. Premier jour et pas horaire",
                "fields": [
                    {"key": "first_day_of_week", "label": "Premier jour de la semaine", "type": "select", "options": _FIRST_DAY_OF_THE_WEEK_OPTIONS},
                    {"key": "standard_timeslot_duration", "label": "Pas horaire (minutes)", "type": "select", "options": get_standard_timeslot_duration_options()},
                ],
                "submitLabel": "Suivant",
                "rpc": "rpc_load_day_rows",
                "rpcParams": {"first_day_of_week": "first_day_of_week"},
            },
            {
                "id": "day_hours",
                "title": "2. Heures d'ouverture de l'établissement",
                "fields": [
                    {"key": "day_rows", "label": "Heures d'ouverture", "type": "text", "widget": "list_preview", "fullWidth": True, "widgetParams": _DAY_ROWS_WIDGET_PARAMS},
                ],
                "submitLabel": "Suivant",
                "rpc": "rpc_validate_day_rows",
                "rpcParams": {"day_rows": "day_rows"},
            },
            {
                "id": "breaks",
                "title": "3. Heure des récréations",
                "fields": [
                    {"key": "morning_break_start_minutes_after_midnight", "label": "Récréation du matin", "type": "select", "widget": "timeslot_picker", "widgetParams": {"includeEmpty": True}},
                    {"key": "afternoon_break_start_minutes_after_midnight", "label": "Récréation de l'après-midi", "type": "select", "widget": "timeslot_picker", "widgetParams": {"includeEmpty": True}},
                ],
                "submitLabel": "Suivant",
                "rpc": "rpc_preview_display",
                "rpcParams": {"day_rows": "day_rows", "standard_timeslot_duration": "standard_timeslot_duration"},
            },
            {
                "id": "display_preview",
                "title": "4. Aperçu des horaires affichés",
                "fields": [
                    {"key": "display_rows", "label": "Horaires affichés", "type": "text", "widget": "list_preview", "fullWidth": True, "widgetParams": _DISPLAY_ROWS_WIDGET_PARAMS},
                ],
                "submitLabel": "Suivant",
                "rpc": "rpc_compute_impact",
                "rpcParams": {"day_rows": "day_rows", "standard_timeslot_duration": "standard_timeslot_duration"},
            },
            {
                "id": "confirm",
                "title": "5. Confirmation",
                "fields": [{"key": "confirm_html", "type": "html", "label": " "}],
                "submitLabel": "Confirmer",
                "rpc": "rpc_apply",
                "rpcParams": {
                    "first_day_of_week": "first_day_of_week",
                    "standard_timeslot_duration": "standard_timeslot_duration",
                    "day_rows": "day_rows",
                    "morning_break_start_minutes_after_midnight": "morning_break_start_minutes_after_midnight",
                    "afternoon_break_start_minutes_after_midnight": "afternoon_break_start_minutes_after_midnight",
                    "display_rows": "display_rows",
                },
            },
            {
                "id": "result",
                "title": "6. Résultat",
                "isLast": True,
                "fields": [{"key": "result_html", "type": "html", "label": " "}],
                "submitLabel": "Fermer",
            },
        ],
    }]

    def __init__(self, id, intro_html=None, first_day_of_week=None, standard_timeslot_duration=None,
                 day_rows=None, morning_break_start_minutes_after_midnight=None,
                 afternoon_break_start_minutes_after_midnight=None, display_rows=None,
                 confirm_html=None, result_html=None):
        self.id = id
        self.intro_html = intro_html
        self.first_day_of_week = first_day_of_week
        self.standard_timeslot_duration = standard_timeslot_duration
        self.day_rows = day_rows or []
        self.morning_break_start_minutes_after_midnight = morning_break_start_minutes_after_midnight
        self.afternoon_break_start_minutes_after_midnight = afternoon_break_start_minutes_after_midnight
        self.display_rows = display_rows or []
        self.confirm_html = confirm_html
        self.result_html = result_html

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        from backend.app.models.system_setting import SystemSetting, SystemSettingKey
        first_day = SystemSetting.get_system_setting_value(db, SystemSettingKey.FIRST_DAY_OF_THE_WEEK.value)
        duration = SystemSetting.get_system_setting_value(db, SystemSettingKey.STANDARD_TIMESLOT_DURATION.value)
        morning = SystemSetting.get_system_setting_value(db, SystemSettingKey.HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT.value)
        afternoon = SystemSetting.get_system_setting_value(db, SystemSettingKey.HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT.value)
        return [cls(
            id=1,
            intro_html="<p>Ce wizard paramètre la grille horaire de l'établissement (jours ouverts, récréations, horaires affichés). Rien n'est enregistré avant la dernière étape de confirmation.</p>",
            first_day_of_week=int(first_day) if first_day else 1,
            standard_timeslot_duration=int(duration) if duration else 30,
            morning_break_start_minutes_after_midnight=int(morning) if morning else None,
            afternoon_break_start_minutes_after_midnight=int(afternoon) if afternoon else None,
        )]

    @requires_access("write")
    def rpc_load_day_rows(self, db: Session, first_day_of_week: int) -> dict:
        return {"day_rows": _render_day_rows(db, first_day_of_week)}

    @requires_access("write")
    def rpc_validate_day_rows(self, db: Session, day_rows: list) -> dict:
        """Valide les heures d'ouverture DÈS l'étape 2 (au lieu d'attendre rpc_apply, la toute
        dernière étape) — réutilise GridDaySettings._validate_hours() telle quelle (même règles :
        fermeture obligatoire dès qu'une ouverture est saisie, fermeture > ouverture, multiple du
        pas horaire, ≤ 23h59), sur une instance JAMAIS ajoutée à la session (ni create() ni
        update()) : appel direct de la méthode, aucune écriture, juste sa validation."""
        from backend.app.models.grid_day_settings import GridDaySettings
        for row in day_rows:
            candidate = GridDaySettings(
                day_of_week=row["day_of_week"],
                hour_day_start_minutes_after_midnight=row.get("hour_day_start_minutes_after_midnight"),
                hour_day_end_minutes_after_midnight=row.get("hour_day_end_minutes_after_midnight"),
            )
            candidate._validate_hours(db)
        return {}

    @requires_access("write")
    def rpc_preview_display(self, db: Session, day_rows: list, standard_timeslot_duration: int) -> dict:
        from backend.app.models.system_setting import SystemSetting, SystemSettingKey
        raw = SystemSetting.get_system_setting_value(db, SystemSettingKey.PUBLIC_DISPLAY_HOURS_BY_SEQUENCE.value)
        existing_map = json.loads(raw) if raw else {}
        return {"display_rows": _render_display_rows(day_rows, standard_timeslot_duration, existing_map)}

    @requires_access("write")
    def rpc_compute_impact(self, db: Session, day_rows: list, standard_timeslot_duration: int) -> dict:
        count = _compute_impacted_course_count(db, day_rows, standard_timeslot_duration)
        if count > 0:
            html = (
                f'<p class="wizard-danger-text"><strong>Attention : {count} cours vont être '
                f"dépositionnés</strong> (leur créneau disparaît de la nouvelle grille). "
                f"Cette opération est irréversible. Voulez-vous vraiment confirmer ?</p>"
            )
        else:
            html = '<p class="wizard-danger-text">Aucun cours ne sera dépositionné par ce changement.</p>'
        return {"confirm_html": html}

    @requires_access("write")
    def rpc_apply(
        self, db: Session, first_day_of_week: int, standard_timeslot_duration: int, day_rows: list,
        morning_break_start_minutes_after_midnight, afternoon_break_start_minutes_after_midnight,
        display_rows: list,
    ) -> dict:
        from backend.app.models.system_setting import SystemSetting, SystemSettingKey
        from backend.app.models.grid_day_settings import GridDaySettings
        from backend.app.models.timeslot import Timeslot

        # Ordre imposé : pas horaire -> jours -> récréations -> horaires publics -> régénération
        # des timeslots. Une seule transaction (voir get_db) : toute ValueError plus bas fait
        # tout rollback, rien n'est jamais persisté à moitié.
        duration_setting = db.query(SystemSetting).filter(SystemSetting.key == SystemSettingKey.STANDARD_TIMESLOT_DURATION).first()
        if str(duration_setting.value) != str(standard_timeslot_duration):
            duration_setting.update(db, {"value": str(standard_timeslot_duration)}, bypass_grid_checks=True)

        first_day_setting = db.query(SystemSetting).filter(SystemSetting.key == SystemSettingKey.FIRST_DAY_OF_THE_WEEK).first()
        if first_day_setting:
            first_day_setting.update(db, {"value": str(first_day_of_week)})
        else:
            SystemSetting.create(db, {"key": "FIRST_DAY_OF_THE_WEEK", "value": str(first_day_of_week)})

        for row in day_rows:
            day_settings = db.query(GridDaySettings).filter(GridDaySettings.day_of_week == row["day_of_week"]).first()
            day_settings.update(db, {
                "hour_day_start_minutes_after_midnight": row.get("hour_day_start_minutes_after_midnight"),
                "hour_day_end_minutes_after_midnight": row.get("hour_day_end_minutes_after_midnight"),
            })

        # Filet de sécurité : si SEUL le pas horaire a changé (aucune ligne de jour retouchée),
        # la boucle ci-dessus n'a rien réconcilié — reconcile_all_days couvre malgré tout les 7 jours
        # (no-op sur un jour dont l'amplitude n'a pas bougé, voir Timeslot.update_timeslot_on_weekgrid_change).
        Timeslot.reconcile_all_days(db)

        def _upsert_break(key: str, value):
            setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if value is None or value == "":
                if setting:
                    setting.delete(db)
                return
            if setting:
                setting.update(db, {"value": str(value)}, bypass_grid_checks=True)
            else:
                SystemSetting.create(db, {"key": key, "value": str(value)}, bypass_grid_checks=True)

        _upsert_break(SystemSettingKey.HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT.value, morning_break_start_minutes_after_midnight)
        _upsert_break(SystemSettingKey.HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT.value, afternoon_break_start_minutes_after_midnight)

        # Re-validation MAINTENANT que jours + pas + récréations sont stabilisés (bypass ci-dessus
        # pendant la transition, qui pouvait traverser des états intermédiaires incohérents) —
        # lève si l'état final reste invalide, ce qui fait tout rollback (voir get_db).
        for key in (
            SystemSettingKey.HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT.value,
            SystemSettingKey.HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT.value,
        ):
            setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if setting and setting.value:
                SystemSetting._validate_break_start(db, key, setting.value)

        # Le bornage 00:00-23:59 et début < fin est un contrat de widget frontend (ClockTimeField.vue
        # — natif <input type="time"> pour le format, écrêtage réel autour de widgetParams.anchorField
        # — real_start/real_end_minutes_after_midnight — pour l'ordre début/fin), pas une règle
        # métier : ce champ ne pilote qu'un affichage (spec.md §0bis), rien côté solveur ne dépend
        # de sa cohérence — pas de revalidation dupliquée ici.
        display_map = {
            str(r["sequence_number"]): [r["public_display_start_minutes_after_midnight"], r["public_display_end_minutes_after_midnight"]]
            for r in display_rows
        }
        display_value = json.dumps(display_map)
        display_setting = db.query(SystemSetting).filter(SystemSetting.key == SystemSettingKey.PUBLIC_DISPLAY_HOURS_BY_SEQUENCE).first()
        if display_setting:
            display_setting.update(db, {"value": display_value})
        else:
            SystemSetting.create(db, {"key": "PUBLIC_DISPLAY_HOURS_BY_SEQUENCE", "value": display_value})

        html = "<p><strong>Grille horaire mise à jour.</strong></p>"
        return {
            "result_html": html,
            "mutated_resources": ["timeslots", "grid_day_settings", "system_settings", "courses"],
        }

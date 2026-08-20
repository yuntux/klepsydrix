def minutes_to_hours(minutes: int) -> tuple[float, str]:
    """
    Convertit une durée exprimée en minutes en un couple (heures décimales, texte HhMM).
    L'heure n'est jamais paddée (1 chiffre en dessous de 10h, davantage au-delà), et les
    minutes sont omises quand la durée tombe sur un nombre exact d'heures.
    Ex: 90 -> (1.5, "1h30"), 60 -> (1.0, "1h"), 630 -> (10.5, "10h30").
    """
    hours_float = minutes / 60.0
    h = minutes // 60
    m = minutes % 60
    hours_text = f"{h}h" if m == 0 else f"{h}h{m:02d}"
    return hours_float, hours_text


# Bornes historiques de SystemSetting.update() (STANDARD_TIMESLOT_DURATION) — seule source de
# vérité, reprise ici pour ne pas dupliquer 5/60 en dur dans la liste déroulante du wizard de
# paramétrage de grille (get_standard_timeslot_duration_options ci-dessous).
STANDARD_TIMESLOT_DURATION_MIN_MINUTES = 5
STANDARD_TIMESLOT_DURATION_MAX_MINUTES = 60


def get_standard_timeslot_duration_options() -> list[dict]:
    """Valeurs valides de pas horaire — diviseurs de 60 minutes compris entre les bornes
    ci-dessus, pour que la journée puisse toujours être calée sur des heures pleines. Pas de
    mirroir JS : contrairement à getDurationOptions (duration.ts), qui doit se recalculer
    côté client à chaque changement du pas courant, cette liste est transmise telle quelle au
    frontend comme `options` statiques du champ (wizard_grid_settings.py), jamais recalculée
    en JS."""
    return [
        {"value": d, "label": f"{d} min"}
        for d in range(STANDARD_TIMESLOT_DURATION_MIN_MINUTES, STANDARD_TIMESLOT_DURATION_MAX_MINUTES + 1)
        if 60 % d == 0
    ]


def validate_multiple_of_standard_timeslot(db, minutes: int, field_label: str):
    """
    Lève une ValueError si `minutes` n'est pas un multiple exact de STANDARD_TIMESLOT_DURATION.
    `field_label` doit être un groupe nominal complet (ex: "La durée du cours"), concaténé
    ci-dessous avec la valeur et le rappel du créneau standard.
    """
    from backend.app.models.system_setting import SystemSetting
    val = SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION")
    duration = int(val)
    if minutes % duration != 0:
        raise ValueError(f"{field_label} ({minutes} min) doit être un multiple exact du créneau standard ({duration} min).")


DAY_NAMES = {1: "Lundi", 2: "Mardi", 3: "Mercredi", 4: "Jeudi", 5: "Vendredi", 6: "Samedi", 7: "Dimanche"}


def day_of_week_label(day_of_week: int) -> str:
    """Jour de la semaine en toutes lettres. Convention day_of_week: 1=lundi ... 7=dimanche,
    partagée par Timeslot.day_of_week et GridDaySettings.day_of_week — seule source de vérité
    pour ce libellé, à ne pas dupliquer ailleurs (mirroir JS : frontend/src/utils/date.ts)."""
    return DAY_NAMES.get(day_of_week, f"Jour {day_of_week}")


def get_first_day_of_week(db) -> int:
    """Valeur courante du réglage système FIRST_DAY_OF_THE_WEEK (1=lundi ... 7=dimanche),
    repli sur 1 (lundi) tant que le réglage n'a pas été saisi."""
    from backend.app.models.system_setting import SystemSetting
    val = SystemSetting.get_system_setting_value(db, "FIRST_DAY_OF_THE_WEEK")
    return int(val) if val else 1


def day_of_week_sort_key(day_of_week: int, first_day_of_week: int) -> int:
    """Position 0-based d'un jour dans une semaine d'affichage qui commence à
    `first_day_of_week` — clé de tri partout où l'ordre des jours doit refléter
    FIRST_DAY_OF_THE_WEEK (grille écran, rapports imprimés). Convention day_of_week identique à
    day_of_week_label ci-dessus. Mirroir JS : frontend/src/utils/date.ts::dayOfWeekSortKey."""
    return (day_of_week - first_day_of_week) % 7

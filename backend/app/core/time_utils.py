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


def get_duration_options(include_zero: bool = False):
    """
    Options d'un champ durée en minutes, par pas de STANDARD_TIMESLOT_DURATION jusqu'à 8h — pour
    tout champ dont les valeurs doivent tomber sur une frontière de créneau (voir
    validate_multiple_of_standard_timeslot ci-dessous, qui l'impose en base). Partagée par
    Course.duration_minutes, ServiceRepartition.duration_minutes, et les champs
    weekly_duration_*_minutes de Service/MefService.

    include_zero : à True pour les champs où 0 est une valeur valide signifiant "modalité non
    utilisée" (les weekly_duration_*_minutes, qui valent 0 par défaut) — jamais pour un champ où
    une durée nulle n'a pas de sens (Course/ServiceRepartition).
    """
    from backend.app.core.database import SessionLocal
    from backend.app.models.system_setting import SystemSetting
    db = SessionLocal()
    try:
        val = SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION")
        step = int(val)

        def format_duration(minutes):
            if minutes >= 60:
                return minutes_to_hours(minutes)[1]
            return f"{minutes} min"

        # Générer des options jusqu'à 8 heures (480 minutes)
        max_duration_minutes = 480
        num_slots = max_duration_minutes // step
        options = [{"value": step * i, "label": format_duration(step * i)} for i in range(1, num_slots + 1)]
        if include_zero:
            options.insert(0, {"value": 0, "label": "Aucune"})
        return options
    finally:
        db.close()


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

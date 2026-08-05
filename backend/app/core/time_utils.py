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

"""
Rapport « Grille d'emploi du temps » — mutualisé sur les 7 ressources pouvant être liées à un cours
(`Course._RESOURCE_RELATIONS` + `classroom_requirements`, voir course.py) : Teacher,
NonTeachingStaff, Classroom, Material, Division, Group, ClassPart. Un seul gabarit
(`templates/timetable.html`), une seule logique de génération ici, paramétrée par modèle — voir
`REGISTRY` dans `reports/__init__.py` pour les 7 entrées (une par modèle, imposé par la sécurité :
`ReportDef.model` détermine le `browse()`/`read()` appliqué, voir reports/base.py).

Comme `course_list.py`, jamais de traversée de relation ORM pour aller chercher les cours d'une
ressource (contournerait le domaine d'accès de `Course`, voir reports/base.py) : seules les tables
d'association (colonnes brutes) servent à corréler des ids, la lecture réelle des cours passe par
`Course.read()`/`browse()`.

Positionnement en POURCENTAGE (pas de `<tr>` par créneau) : chaque colonne jour est un unique
conteneur `position: relative` sur toute la hauteur de la grille, dans lequel créneaux gris
(inactifs), trait de récréation et boîtes de cours sont positionnés en `top`/`height`/`left`/`width`
absolus — seule façon d'obtenir une hauteur de boîte proportionnelle à la durée réelle du cours (un
cours d'1h doit être deux fois plus haut qu'un cours de 30 min) tout en gardant plusieurs cours
parallèles (ex: semaine A / semaine B sur le même créneau) côte à côte. Mêmes données que celles
utilisées par la grille écran (voir useTimeslotGrid.ts, BaseGrid.vue, CourseCard.vue), reconstruites
côté serveur car le rendu HTML/CSS de WeasyPrint n'exécute aucun JS.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.time_utils import day_of_week_label, day_of_week_sort_key, get_first_day_of_week
from backend.app.models.classroom import Classroom
from backend.app.models.course import (
    Course,
    course_class_parts,
    course_divisions,
    course_groups,
    course_materials,
    course_non_teaching_staffs,
    course_teachers,
)
from backend.app.models.course_classroom_requirement import CourseClassroomRequirement
from backend.app.models.division import Division
from backend.app.models.group import ClassPart, Group
from backend.app.models.material import Material
from backend.app.models.non_teaching_staff import NonTeachingStaff
from backend.app.models.school import School
from backend.app.models.subject import Subject
from backend.app.models.system_setting import SystemSetting
from backend.app.models.teacher import Teacher
from backend.app.models.timeslot import Timeslot
from backend.app.reports.base import ReportDef

# Table d'association + colonne pointant vers la ressource, par modèle — Classroom est à part
# (CourseClassroomRequirement est une vraie entité, pas une table d'association pure, voir
# course_classroom_requirement.py).
_ASSOCIATION_BY_MODEL = {
    Teacher: (course_teachers, "teacher_id"),
    NonTeachingStaff: (course_non_teaching_staffs, "non_teaching_staff_id"),
    Material: (course_materials, "material_id"),
    Division: (course_divisions, "division_id"),
    Group: (course_groups, "group_id"),
    ClassPart: (course_class_parts, "class_part_id"),
}

# Règle de couleur (confirmée avec l'utilisateur) : imprimer l'EDT d'une ressource qui SERT des
# classes (professeur, personnel, salle, matériel) colore chaque cours par la classe concernée ;
# imprimer l'EDT d'une ressource qui EST une audience (classe, groupe, partie de classe) colore
# chaque cours par sa matière — voir _class_color_for_course / _subject_color_for_course.
_COLOR_MODE_BY_MODEL = {
    Teacher: "class",
    NonTeachingStaff: "class",
    Classroom: "class",
    Material: "class",
    Division: "subject",
    Group: "subject",
    ClassPart: "subject",
}

# Titre fusionné par page (voir timetable.html) : "Emploi du temps — {type} {ressource}", ex.
# "Emploi du temps — Division 6A" — le nom seul ne dit pas de quel type de ressource il s'agit
# (« 6A » pourrait être une classe ou un groupe).
_RESOURCE_TYPE_LABEL_BY_MODEL = {
    Teacher: "Professeur",
    NonTeachingStaff: "Personnel non enseignant",
    Classroom: "Salle",
    Material: "Matériel",
    Division: "Division",
    Group: "Groupe",
    ClassPart: "Partie de classe",
}

# Boîte de cours (voir _course_box_lines) : quelle catégorie de ressource se tait quand on imprime
# SA PROPRE grille et que le cours ne porte qu'UNE seule ressource de cette catégorie, précisément
# celle imprimée (ex: la grille du professeur Dupont n'affiche pas « Dupont » sur chacun de ses
# cours) — confirmé avec l'utilisateur, ClassPart et Material n'ont volontairement pas cette
# exception (Material n'est de toute façon jamais affiché sur la boîte, voir plus bas).
_SUPPRESS_KEY_BY_MODEL = {
    Division: "division",
    Group: "group",
    Classroom: "classroom",
    Teacher: "teacher",
    NonTeachingStaff: "staff",
}


def _course_ids_for_resource(db: Session, model: type, resource_ids: list) -> set:
    if not resource_ids:
        return set()
    if model is Classroom:
        rows = db.execute(
            select(CourseClassroomRequirement.course_id).where(
                CourseClassroomRequirement.classroom_id.in_(resource_ids)
            )
        )
    else:
        table, column = _ASSOCIATION_BY_MODEL[model]
        rows = db.execute(select(table.c.course_id).where(getattr(table.c, column).in_(resource_ids)))
    return {row[0] for row in rows}


def _leaf_courses_for_resource(db: Session, model: type, resource_id: int) -> list:
    """
    Cours « feuilles » (sans enfant — `not is_composed`, un cours composé parent n'a pas d'horaire
    propre à imprimer) et placés (`timeslot_id` non nul) de cette ressource. `is_composed` est une
    colonne déjà stockée sur Course (voir course.py::_compute_is_composed), aucune traversée
    supplémentaire n'est nécessaire pour l'exclure des cours parents.
    """
    candidate_ids = _course_ids_for_resource(db, model, [resource_id])
    if not candidate_ids:
        return []
    courses = Course.read(db, domain={"id": list(candidate_ids)})
    return [c for c in courses if c.timeslot_id is not None and not c.is_composed]


def _resolve_association(db: Session, table, column: str, model: type, course_ids: list) -> tuple:
    """Corrélation cours -> ressource par lecture dédiée (voir docstring de module) : un `id_map`
    (course_id -> [related_id, ...]) tiré de la table d'association brute, puis un `by_id`
    (related_id -> instance) tiré d'un SEUL `model.read()` par lot — jamais `course.<relation>`."""
    id_map: dict = {}
    for row in db.execute(select(table.c.course_id, getattr(table.c, column)).where(table.c.course_id.in_(course_ids))):
        id_map.setdefault(row[0], []).append(row[1])
    all_ids = {rid for ids in id_map.values() for rid in ids}
    by_id = {m.id: m for m in model.read(db, domain={"id": list(all_ids)})} if all_ids else {}
    return id_map, by_id


def _resolve_classroom_requirements(db: Session, course_ids: list) -> tuple:
    """Symétrique de _resolve_association pour Classroom, dont la corrélation passe par
    CourseClassroomRequirement (une vraie entité) plutôt qu'une table d'association pure."""
    id_map: dict = {}
    rows = db.execute(
        select(CourseClassroomRequirement.course_id, CourseClassroomRequirement.classroom_id)
        .where(CourseClassroomRequirement.course_id.in_(course_ids))
    )
    for row in rows:
        id_map.setdefault(row[0], []).append(row[1])
    all_ids = {rid for ids in id_map.values() for rid in ids}
    by_id = {c.id: c for c in Classroom.read(db, domain={"id": list(all_ids)})} if all_ids else {}
    return id_map, by_id


def _resolve_course_labels(db: Session, courses: list) -> dict:
    """
    Une seule collecte, réutilisée à la fois pour la couleur (_class_color_for_course /
    _subject_color_for_course) et pour le contenu texte de chaque boîte de cours
    (_course_box_lines) — évite de relire deux fois les mêmes tables d'association.
    """
    course_ids = [c.id for c in courses]
    empty = ({}, {})
    if not course_ids:
        return {
            "subject_by_id": {}, "division": empty, "group": empty,
            "classroom": empty, "teacher": empty, "staff": empty,
        }

    subject_ids = {c.subject_id for c in courses if c.subject_id is not None}
    subject_by_id = {s.id: s for s in Subject.read(db, domain={"id": list(subject_ids)})} if subject_ids else {}

    return {
        "subject_by_id": subject_by_id,
        "division": _resolve_association(db, course_divisions, "division_id", Division, course_ids),
        "group": _resolve_association(db, course_groups, "group_id", Group, course_ids),
        "classroom": _resolve_classroom_requirements(db, course_ids),
        "teacher": _resolve_association(db, course_teachers, "teacher_id", Teacher, course_ids),
        "staff": _resolve_association(db, course_non_teaching_staffs, "non_teaching_staff_id", NonTeachingStaff, course_ids),
    }


def _class_color_for_course(course, labels: dict):
    group_ids, groups_by_id = labels["group"]
    g_ids = group_ids.get(course.id, [])
    if len(g_ids) == 1:
        group = groups_by_id.get(g_ids[0])
        return group.color if group else None
    if len(g_ids) >= 2:
        return None

    division_ids, divisions_by_id = labels["division"]
    d_ids = division_ids.get(course.id, [])
    if len(d_ids) == 1:
        division = divisions_by_id.get(d_ids[0])
        return division.color if division else None
    return None


def _subject_color_for_course(course, labels: dict):
    subject = labels["subject_by_id"].get(course.subject_id)
    return subject.color if subject else None


def _course_box_lines(course, labels: dict, printed_model: type, printed_resource_id: int) -> list:
    """
    Contenu texte d'une boîte de cours : matière puis, dans l'ordre, classes/groupes/salles/
    professeurs/personnel — jamais le matériel (voir _ASSOCIATION_BY_MODEL, volontairement absent
    d'ici). Une catégorie est omise soit parce que le cours n'y a AUCUNE ressource, soit parce
    qu'elle serait redondante avec la grille imprimée elle-même (voir _SUPPRESS_KEY_BY_MODEL).
    """
    lines = []
    subject = labels["subject_by_id"].get(course.subject_id)
    if subject:
        lines.append(subject.short_name or subject.name)

    for key in ("division", "group", "classroom", "teacher", "staff"):
        id_map, by_id = labels[key]
        ids = id_map.get(course.id, [])
        if not ids:
            continue
        if _SUPPRESS_KEY_BY_MODEL.get(printed_model) == key and len(ids) == 1 and ids[0] == printed_resource_id:
            continue
        names = [by_id[rid].display_name for rid in ids if rid in by_id]
        if names:
            lines.append(", ".join(names))
    return lines


def _week_badge(course):
    value = course.week_type.value if hasattr(course.week_type, "value") else course.week_type
    return value if value in ("A", "B") else None


def _format_minutes(minutes) -> str:
    """Case blanche (pas de repli) si `minutes` est None — voir Timeslot.public_display_*, une
    valeur explicitement absente du réglage PUBLIC_DISPLAY_HOURS_BY_SEQUENCE."""
    if minutes is None:
        return ""
    hours, mins = divmod(int(minutes), 60)
    return f"{hours:02d}h{mins:02d}"


def _sequence_rows(all_timeslots: list) -> list:
    """
    Axe des lignes : une par numéro de séquence intra-journée existant dans la grille (voir
    Timeslot.intraday_sequence_number) — la grille COMPLÈTE (cases vides comprises), pas seulement
    les créneaux occupés par la ressource imprimée, cohérent avec la grille écran.
    """
    rows_by_sequence = {}
    for ts in all_timeslots:
        seq = ts.intraday_sequence_number
        if seq is None or seq in rows_by_sequence:
            continue
        rows_by_sequence[seq] = {
            "sequence": seq,
            "start_label": _format_minutes(ts.public_display_start_minutes_after_midnight),
            "end_label": _format_minutes(ts.public_display_end_minutes_after_midnight),
        }
    return [rows_by_sequence[seq] for seq in sorted(rows_by_sequence)]


def _build_hour_rows(row_templates: list) -> list:
    """
    Ajoute la géométrie (position en % de la hauteur totale de la grille) à chaque ligne, et
    calcule `show_divider_after` : le trait horizontal séparant cette ligne de la suivante est
    supprimé quand l'heure de fin de celle-ci ET l'heure de début de la suivante sont TOUTES LES
    DEUX blanches (aucune information ne serait perdue à l'omettre — voir _format_minutes) — sinon
    la grille imprimée serait striée de traits ne correspondant à aucun horaire affiché.
    """
    total = len(row_templates)
    if not total:
        return []
    rows = []
    for idx, row in enumerate(row_templates):
        show_divider_after = None
        if idx < total - 1:
            next_row = row_templates[idx + 1]
            show_divider_after = not (row["end_label"] == "" and next_row["start_label"] == "")
        rows.append({
            **row,
            "top_pct": idx / total * 100,
            "bottom_pct": (idx + 1) / total * 100,
            "show_divider_after": show_divider_after,
        })
    return rows


def _inactive_blocks(day_value: int, row_templates: list, existing_day_seq: set, total_rows: int) -> list:
    """Plages grisées (voir isTimeslotActive côté écran, useTimeslotGrid.ts) — runs contigus
    fusionnés en un seul bloc plutôt qu'un div par ligne, pour un gabarit plus léger."""
    if not total_rows:
        return []
    blocks = []
    run_start = None
    for row_index, row in enumerate(row_templates):
        active = (day_value, row["sequence"]) in existing_day_seq
        if not active and run_start is None:
            run_start = row_index
        elif active and run_start is not None:
            blocks.append({"top_pct": run_start / total_rows * 100, "height_pct": (row_index - run_start) / total_rows * 100})
            run_start = None
    if run_start is not None:
        blocks.append({"top_pct": run_start / total_rows * 100, "height_pct": (total_rows - run_start) / total_rows * 100})
    return blocks


def _break_lines(db: Session, show_breaks: bool, duration, min_start, total_rows: int) -> list:
    """
    Trait de récréation (voir BaseGrid.vue::displayBreaks, activé par défaut) — converti d'une
    minute absolue en position de FRONTIÈRE de ligne (`(minute - min_start) / duration`, un flottant
    : la récréation ne tombe pas forcément pile sur une frontière de créneau) puis en % de la
    hauteur totale, exactement comme un cours ou un créneau. `row_index` (le créneau qui CONTIENT
    cette position, pas une frontière entre deux créneaux comme pour un séparateur normal) sert à
    déterminer, par jour, si la ligne tombe sur une case grisée (voir _day_lines ci-dessous).
    """
    if not show_breaks or not total_rows or not duration or min_start is None:
        return []
    lines = []
    for key in (
        "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT",
        "HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT",
    ):
        raw = SystemSetting.get_system_setting_value(db, key)
        if not raw:
            continue
        offset = (int(raw) - min_start) / duration
        if 0 <= offset <= total_rows:
            row_index = min(max(int(offset), 0), total_rows - 1)
            lines.append({"top_pct": offset / total_rows * 100, "row_index": row_index})
    return lines


def _day_lines(day_value: int, hour_rows: list, row_templates: list, existing_day_seq: set, break_lines: list) -> tuple:
    """
    Séparateurs de créneaux + traits de récréation POUR CETTE COLONNE JOUR — jamais sur une case
    grisée (aucun des deux créneaux adjacents à la frontière n'est ouvert ce jour-là). Rendus comme
    boîte de cours (voir timetable.html) : un simple z-index (2 pour .timetable-course-box, contre 1
    ici) suffit alors à les faire disparaître sous un cours qui les recouvre — vérifié rendu réel
    (rasterisation PDF) plutôt que supposé. Une PRÉCÉDENTE version posait le séparateur en un seul
    bloc pleine largeur, enfant direct de .timetable-body-row (donc PAS un frère direct des boîtes
    de cours, imbriquées deux niveaux plus bas dans chaque colonne jour) : le z-index n'était alors
    PAS respecté de façon fiable par WeasyPrint à travers cette limite de sous-arbre — constaté par
    rasterisation, un trait traversait visiblement un cours malgré z-index inférieur. Le replacer en
    enfant direct de CHAQUE .timetable-day-col (frère immédiat des boîtes de cours qu'il doit pouvoir
    recouvrir, exactement comme .timetable-break-line — jamais pris en défaut, seul le séparateur
    l'était) restaure un empilement fiable, sans aucun découpage géométrique à faire ici.

    Retourne (dividers, breaks), chacun `[{top_pct}, ...]`.
    """
    total_rows = len(row_templates)

    def _seq_active(row_index):
        if row_index is None or not (0 <= row_index < total_rows):
            return False
        return (day_value, row_templates[row_index]["sequence"]) in existing_day_seq

    dividers = []
    for idx, row in enumerate(hour_rows):
        if not row["show_divider_after"]:
            continue
        # Frontière entre la ligne idx et idx+1 : visible pour ce jour si AU MOINS un des deux
        # créneaux adjacents y est ouvert (sinon la frontière est entièrement dans une case grisée).
        if _seq_active(idx) or _seq_active(idx + 1):
            dividers.append({"top_pct": row["bottom_pct"]})

    breaks = [{"top_pct": line["top_pct"]} for line in break_lines if _seq_active(line["row_index"])]

    return dividers, breaks


def _group_courses_by_day(courses: list, timeslots_by_id: dict, seq_to_row_index: dict) -> dict:
    by_day: dict = {}
    for course in courses:
        ts = timeslots_by_id.get(course.timeslot_id)
        if ts is None:
            continue
        row_index = seq_to_row_index.get(ts.intraday_sequence_number)
        if row_index is None:
            continue
        by_day.setdefault(ts.day_of_week, []).append((course, row_index))
    return by_day


def _layout_course_boxes(
    entries: list, total_rows: int, std_duration, labels: dict, color_mode: str,
    printed_model: type, printed_resource_id: int,
) -> list:
    """
    Hauteur proportionnelle à la durée réelle (`span` créneaux, jamais 1 créneau fixe) + cours
    parallèles côte à côte (ex: semaine A / semaine B sur le même horaire) — même modèle que
    CourseCard.vue (`overlapIndex`/`overlapCount`, largeur égale entre cours d'un même groupe de
    recouvrement, pas un algorithme de compactage plus fin).
    """
    if not entries or not total_rows or not std_duration:
        return []

    scored = []
    for course, row_index in entries:
        span = max(1, round(course.duration_minutes / std_duration))
        scored.append({"course": course, "row_index": row_index, "span": span})
    scored.sort(key=lambda e: e["row_index"])

    clusters = []
    current: list = []
    cluster_end = -1
    for entry in scored:
        if current and entry["row_index"] < cluster_end:
            current.append(entry)
            cluster_end = max(cluster_end, entry["row_index"] + entry["span"])
        else:
            if current:
                clusters.append(current)
            current = [entry]
            cluster_end = entry["row_index"] + entry["span"]
    if current:
        clusters.append(current)

    boxes = []
    for cluster in clusters:
        count = len(cluster)
        for idx, entry in enumerate(cluster):
            course = entry["course"]
            color = (
                _class_color_for_course(course, labels) if color_mode == "class"
                else _subject_color_for_course(course, labels)
            )
            boxes.append({
                "top_pct": entry["row_index"] / total_rows * 100,
                "height_pct": entry["span"] / total_rows * 100,
                "left_pct": idx / count * 100,
                "width_pct": 100 / count,
                "color": color,
                "lines": _course_box_lines(course, labels, printed_model, printed_resource_id),
                "week_badge": _week_badge(course),
            })
    return boxes


def get_values_factory(model: type):
    """Construit le `get_values(db, ids, params)` d'un `ReportDef` pour `model` — toute la logique
    (résolution des cours, grille jours/séquences, couleur, contenu des boîtes) est écrite une
    seule fois ci-dessus et partagée par les 7 entrées du registre, seul le modèle (donc la table
    d'association et le mode de couleur) change d'un appel à l'autre."""
    color_mode = _COLOR_MODE_BY_MODEL[model]

    def get_values(db: Session, ids: list, params: dict) -> dict:
        resources = model.browse(db, ids) if ids else model.read(db)

        show_breaks = params.get("show_breaks", True) if params else True

        all_timeslots = Timeslot.read(db)
        first_day = get_first_day_of_week(db)
        # Colonnes jour : uniquement celles ayant AU MOINS un créneau en base — un jour de la
        # semaine sans aucun Timeslot (ex: dimanche) n'a pas sa place dans la grille imprimée, tout
        # comme la grille écran (useTimeslotGrid.ts::days, dérivé des mêmes Timeslot).
        days_present = sorted({t.day_of_week for t in all_timeslots}, key=lambda d: day_of_week_sort_key(d, first_day))
        days = [{"value": d, "label": day_of_week_label(d)} for d in days_present]

        row_templates = _sequence_rows(all_timeslots)
        total_rows = len(row_templates)
        hour_rows = _build_hour_rows(row_templates)
        seq_to_row_index = {row["sequence"]: idx for idx, row in enumerate(row_templates)}
        timeslots_by_id = {t.id: t for t in all_timeslots}
        existing_day_seq = {
            (t.day_of_week, t.intraday_sequence_number) for t in all_timeslots
            if t.intraday_sequence_number is not None
        }

        duration, min_start, _display = all_timeslots[0]._grid_context(db) if all_timeslots else (None, None, {})
        std_duration = int(duration) if duration else None
        break_lines = _break_lines(db, show_breaks, std_duration, min_start, total_rows)

        day_meta = {}
        for day in days:
            dividers, breaks = _day_lines(day["value"], hour_rows, row_templates, existing_day_seq, break_lines)
            day_meta[day["value"]] = {
                "label": day["label"],
                "inactive_blocks": _inactive_blocks(day["value"], row_templates, existing_day_seq, total_rows),
                "dividers": dividers,
                "breaks": breaks,
            }

        # Établissement DE LA RESSOURCE imprimée (voir en-tête courant, base.py::_page_chrome_css)
        # — Teacher/NonTeachingStaff/Classroom/Division portent un school_id direct ; Material/Group/
        # ClassPart n'en ont aucun (pas de traversée indirecte via une relation pour ces derniers,
        # conformément à "si elle est liée à un établissement" : simplement rien à afficher alors).
        resource_school_ids = {resource.school_id for resource in resources if getattr(resource, "school_id", None)}
        resource_schools_by_id = {s.id: s for s in School.read(db, domain={"id": list(resource_school_ids)})} if resource_school_ids else {}

        pages = []
        for resource in resources:
            courses = _leaf_courses_for_resource(db, model, resource.id)
            labels = _resolve_course_labels(db, courses)
            courses_by_day = _group_courses_by_day(courses, timeslots_by_id, seq_to_row_index)

            day_columns = []
            for day in days:
                entries = courses_by_day.get(day["value"], [])
                boxes = _layout_course_boxes(entries, total_rows, std_duration, labels, color_mode, model, resource.id)
                meta = day_meta[day["value"]]
                day_columns.append({
                    "value": day["value"],
                    "label": meta["label"],
                    "inactive_blocks": meta["inactive_blocks"],
                    "dividers": meta["dividers"],
                    "breaks": meta["breaks"],
                    "courses": boxes,
                })

            resource_name = f"{_RESOURCE_TYPE_LABEL_BY_MODEL[model]} {resource.display_name}"
            resource_school = resource_schools_by_id.get(getattr(resource, "school_id", None))
            pages.append({
                "resource_name": resource_name,
                "resource_school_name": resource_school.display_name if resource_school else "",
                "day_columns": day_columns,
            })

        schools = School.read(db)
        return {
            "report_title": "Emploi du temps",
            "days": days,
            "hour_rows": hour_rows,
            "pages": pages,
            "school_name": schools[0].display_name if len(schools) == 1 else "",
        }

    return get_values


def filename(db: Session, ids: list) -> str:
    return f"emploi-du-temps-{datetime.now().strftime('%Y-%m-%d')}.pdf"


def _no_document_title(db: Session, ids: list) -> str:
    """Chaque page rend son propre en-tête compact (titre + nom de la ressource fusionnés sur une
    ligne, voir timetable.html::timetable-page-title) — le <h1> générique de layout.html ferait
    doublon. Une chaîne vide supprime le <h1> (voir layout.html, `{% if title %}`)."""
    return ""


def _report_for(model: type, name: str, label: str) -> ReportDef:
    return ReportDef(
        name=name,
        label=label,
        model=model,
        template="timetable.html",
        get_values=get_values_factory(model),
        filename=filename,
        paperformat="a4-landscape",
        document_title=_no_document_title,
        extra_css="timetable.css",
    )


REPORT_TEACHER = _report_for(Teacher, "timetable_teacher", "Emploi du temps (professeur)")
REPORT_NON_TEACHING_STAFF = _report_for(NonTeachingStaff, "timetable_non_teaching_staff", "Emploi du temps (personnel)")
REPORT_CLASSROOM = _report_for(Classroom, "timetable_classroom", "Emploi du temps (salle)")
REPORT_MATERIAL = _report_for(Material, "timetable_material", "Emploi du temps (matériel)")
REPORT_DIVISION = _report_for(Division, "timetable_division", "Emploi du temps (classe)")
REPORT_GROUP = _report_for(Group, "timetable_group", "Emploi du temps (groupe)")
REPORT_CLASS_PART = _report_for(ClassPart, "timetable_class_part", "Emploi du temps (partie de classe)")

ALL_REPORTS = [
    REPORT_TEACHER,
    REPORT_NON_TEACHING_STAFF,
    REPORT_CLASSROOM,
    REPORT_MATERIAL,
    REPORT_DIVISION,
    REPORT_GROUP,
    REPORT_CLASS_PART,
]

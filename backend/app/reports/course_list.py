"""
Rapport « Liste des cours » — nom du cours et horaire. Premier rapport du socle, volontairement
minimal : il sert autant à imprimer une liste qu'à valider le socle en conditions réelles
(pagination sur plusieurs pages, en-tête de tableau répété, accents).
"""
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.core.time_utils import day_of_week_sort_key, get_first_day_of_week
from backend.app.models.course import Course
from backend.app.models.school import School
from backend.app.models.timeslot import Timeslot
from backend.app.reports.base import ReportDef


def _timeslots_by_id(db: Session, ids: set) -> dict:
    """
    Résout les créneaux par lecture DÉDIÉE plutôt que par traversée de relation (`course.timeslot`)
    : voir reports/base.py, le moteur de droits ne s'applique qu'à `read()`. Un créneau que
    l'utilisateur n'a pas le droit de lire est simplement absent du dictionnaire — l'appelant
    retombe sur « Non placé », il ne voit pas un libellé qu'il n'aurait pas dû voir.

    Retourne le libellé ET la clé de tri chronologique, tirés du même enregistrement : trier sur le
    libellé donnerait un ordre ALPHABÉTIQUE des jours (« Jeudi, Lundi, Mardi… »), ce qui passe pour
    un défaut sur une liste imprimée. La clé de tri respecte FIRST_DAY_OF_THE_WEEK (voir
    time_utils.day_of_week_sort_key) plutôt que l'ordre brut 1=lundi..7=dimanche, pour que
    l'imprimé retombe sur le même ordre de jours que la grille écran.
    """
    if not ids:
        return {}
    first_day = get_first_day_of_week(db)
    return {
        timeslot.id: {
            "label": timeslot.display_name,
            "sort_key": (day_of_week_sort_key(timeslot.day_of_week, first_day), timeslot.minutes_from_midnight),
        }
        for timeslot in Timeslot.read(db, domain={"id": list(ids)})
    }


def get_values(db: Session, ids: list, params: dict) -> dict:
    """
    Pendant de `_get_report_values()` d'Odoo.

    `ids` vide = imprimer tout ce que l'utilisateur a le droit de voir (une RECHERCHE, filtrage
    silencieux normal). `ids` fourni = une DÉSIGNATION : `browse()` refuse si l'un d'eux est
    inaccessible, pour ne jamais produire un PDF amputé d'apparence complète (voir
    architecture.md §18.I).
    """
    courses = Course.browse(db, ids) if ids else Course.read(db)

    # `Course.name` est un libellé DÉNORMALISÉ, recomposé à chaque écriture par
    # Course.compute_name() (« Mathématiques - 6ème A - Dupont ») : il est donc déjà résolu en
    # base, aucune matière ni division à aller rechercher ici. Le repli sur l'identifiant ne sert
    # qu'aux lignes antérieures à ce mécanisme, la colonne restant nullable au schéma.
    timeslots = _timeslots_by_id(db, {c.timeslot_id for c in courses if c.timeslot_id})

    lines = []
    for course in courses:
        timeslot = timeslots.get(course.timeslot_id)
        lines.append({
            "name": course.name or f"Cours n°{course.id}",
            "schedule": timeslot["label"] if timeslot else "Non placé",
            # Clé de tri non rendue : les cours non placés passent en fin de liste, les autres
            # dans l'ordre chronologique réel (jour, puis heure). Le nom départage à horaire égal,
            # pour que deux éditions successives donnent le même document.
            "_sort_key": (0, *timeslot["sort_key"]) if timeslot else (1, 0, 0),
        })
    lines.sort(key=lambda line: (line["_sort_key"], line["name"]))

    schools = School.read(db)
    return {
        "lines": lines,
        "school_name": schools[0].display_name if len(schools) == 1 else "",
    }


def filename(db: Session, ids: list) -> str:
    return f"liste-des-cours-{datetime.now().strftime('%Y-%m-%d')}.pdf"


REPORT = ReportDef(
    name="course_list",
    label="Liste des cours",
    model=Course,
    template="course_list.html",
    get_values=get_values,
    filename=filename,
    paperformat="a4-portrait",
)

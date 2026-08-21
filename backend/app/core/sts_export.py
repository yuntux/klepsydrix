"""
Génération du flux STS-web montant : `emp_sts_<RNE>_<ANNEE>.xml`, racine `EDT_STS`.

Sens **montant** uniquement — de Klepsydrix vers STS-web. Le descendant est lu par `sts_flux.py`.
Les deux noms sont anagrammes l'un de l'autre, et les deux racines aussi (`STS_EDT` en descendant,
`EDT_STS` ici) : c'est la confusion la plus fréquente.

> [!WARNING]
> **Ce format est le moins bien connu des deux.** STS-web énumère lui-même quatre familles de
> données au chargement — services, ARE, indemnités, cours et alternances — et seule la dernière,
> plus la coquille des services, a des balises attestées. Elles proviennent du lecteur de CDT_6000,
> unique source disponible sur ce sens. Les ARE, les indemnités, les volumes horaires de service et
> l'effectif d'un groupe ont des balises **inconnues** : ce module ne les écrit pas, et le fichier
> produit est donc partiel par construction.

Deux incertitudes, deux traitements. Une balise dont le **nom** est inconnu n'est pas écrite : lui
en inventer un serait pire que de se taire. Une balise dont le nom est prouvé par le fichier
descendant mais dont la **présence** ici reste supposée est écrite — `DIVISION/MEFS_APPARTENANCE`
et `GROUPE/LIBELLE_LONG`, déclarées facultatives par le schéma (FORMATS_JUSTIFICATION.md §9.11).

**Le document est construit avec ElementTree, jamais par concaténation de chaînes** : c'est
l'arbre qui garantit l'échappement des caractères, la fermeture des balises et l'encodage. Puis il
est **validé contre le schéma** (`schemas/emp_sts.xsd`) avant d'être rendu. Un fichier invalide est
une erreur de programmation ici, pas une donnée mal saisie — d'où une exception explicite plutôt
qu'un fichier douteux transmis à l'académie.

Module **pur** : il lit la base et renvoie une chaîne XML. Il n'écrit rien et n'appelle pas
l'audit — c'est le wizard qui enchaîne les deux.
"""
import pathlib
from xml.etree import ElementTree as ET

ROOT_TAG = "EDT_STS"

SCHEMA_PATH = pathlib.Path(__file__).parent / "schemas" / "emp_sts.xsd"

EN_TETE = (
    " Fichier de remontee STS-web produit par Klepsydrix.\n\n"
    "  ATTENTION : le format du sens montant n'est pas publie par le ministere. Sa structure a\n"
    "  ete deduite du code de deux logiciels libres, GEPI et CDT, et elle est probablement\n"
    "  incomplete. Sur les quatre familles de donnees que STS-web attend (services, ARE,\n"
    "  indemnites, cours et alternances), ce fichier ne porte que les cours, leurs alternances et\n"
    "  la coquille des services : les balises des trois autres sont inconnues.\n"
)


class StsExportError(RuntimeError):
    """Le document produit ne respecte pas le schéma. Message destiné au développeur."""


def _hhmm(minutes) -> str:
    """HHMM sans séparateur, le format du fichier montant — et non 08h30 comme dans EXP_COURS."""
    minutes = max(0, int(minutes or 0))
    return f"{minutes // 60:02d}{minutes % 60:02d}"


def _texte(parent, tag: str, valeur):
    """Sous-élément à contenu textuel. ElementTree échappe lui-même &, < et >."""
    noeud = ET.SubElement(parent, tag)
    noeud.text = "" if valeur is None else str(valeur)
    return noeud


def _courses_a_exporter(db, school) -> list:
    """
    Cours réellement écrits : placés, non composés, non exclus. Les trois niveaux d'exclusion, la
    pondération nulle et la quinzaine non tranchée sont déjà résumés par `is_exported_to_sts`.
    Un cours non placé est ignoré ici : l'audit l'a déjà signalé comme bloquant.
    """
    from backend.app.models.course import Course
    return [
        c for c in db.query(Course).filter(Course.school_id == school.id).all()
        if not c.is_composed and c.is_exported_to_sts and c.timeslot_id is not None
    ]


def _structures_du_cours(course) -> list:
    """
    Structures auxquelles rattacher un cours : ses groupes s'il en a, sinon ses divisions. Un cours
    de groupe se range sous `GROUPE`, un cours de classe entière sous `DIVISION` — c'est
    exactement la dichotomie du fichier.
    """
    if course.groups:
        return [("group", g) for g in course.groups]
    return [("division", d) for d in course.divisions]


def _collecter(db, school) -> tuple:
    """
    Range les cours par (type de structure, structure, matière, modalité, enseignant). Renvoie
    aussi les alternances effectivement employées : n'écrire que celles-là évite de déverser tout
    le référentiel dans un fichier qui n'en utilise que trois.
    """
    par_structure = {}
    alternances = {}

    for course in _courses_a_exporter(db, school):
        subject = course.subject_relation
        # Matière sans code national et cours sans alternance sont deux anomalies bloquantes déjà
        # levées par l'audit. Si l'on arrive ici malgré tout, mieux vaut omettre la séance que
        # d'écrire un service anonyme ou une séance sans calendrier.
        if subject is None or not subject.code_nomenclature or course.alternation is None:
            continue
        alternances[course.alternation.id] = course.alternation

        code_modalite = course.modality.code if course.modality else "CG"
        for kind, structure in _structures_du_cours(course):
            entree = par_structure.setdefault((kind, structure.id), {"structure": structure, "services": {}})
            enseignants = entree["services"].setdefault((subject.code_nomenclature, code_modalite), {})
            for teacher in course.teachers:
                enseignants.setdefault(teacher.id, {"teacher": teacher, "courses": []})["courses"].append(course)

    return par_structure, alternances


def _ajouter_alternances(racine, alternances: dict):
    if not alternances:
        return
    from sqlalchemy.orm import object_session
    from backend.app.models.week_calendar import WeekCalendar

    noeud = ET.SubElement(racine, "ALTERNANCES")
    for alternation in sorted(alternances.values(), key=lambda a: a.code):
        element = ET.SubElement(noeud, "ALTERNANCE", {"CODE": alternation.code})
        _texte(element, "LIBELLE_COURT", alternation.code)
        _texte(element, "LIBELLE_LONG", alternation.name)
        _texte(element, "LIBELLE_EDITION", alternation.long_name or alternation.name)
        semaines = ET.SubElement(element, "SEMAINES")
        db = object_session(alternation)
        lignes = db.query(WeekCalendar).filter(
            WeekCalendar.id.in_(alternation.week_calendar_ids or [0])
        ).order_by(WeekCalendar.begin_date).all()
        for semaine in lignes:
            _texte(semaines, "DATE_DEBUT_SEMAINE", semaine.begin_date.isoformat())


def _ajouter_services(parent, services: dict) -> bool:
    """
    Écrit la section SERVICES. Renvoie faux si elle serait restée vide : le schéma exige au moins
    un SERVICE, et un SERVICE au moins un ENSEIGNANT — c'est à l'appelant de renoncer alors à la
    structure entière plutôt que de produire une coquille invalide.
    """
    noeud = ET.SubElement(parent, "SERVICES")
    for (code_matiere, code_modalite), enseignants in sorted(services.items()):
        service = ET.Element("SERVICE", {
            "CODE_MATIERE": code_matiere, "CODE_MOD_COURS": code_modalite,
        })
        bloc = ET.SubElement(service, "ENSEIGNANTS")
        for entree in sorted(enseignants.values(), key=lambda e: e["teacher"].epp_id or ""):
            teacher = entree["teacher"]
            # Sans identifiant EPP, l'enseignant n'est pas appariable côté académique et l'attribut
            # ID n'a rien à porter. L'audit le signale comme bloquant : ici on se contente de ne
            # pas écrire de ligne fausse.
            if not teacher.epp_id:
                continue
            element = ET.SubElement(bloc, "ENSEIGNANT", {
                "ID": str(teacher.epp_id), "TYPE": "epp" if teacher.is_epp else "local",
            })
            rattaches = ET.SubElement(element, "COURS_RATTACHES")
            seances = sorted(
                entree["courses"],
                key=lambda c: (c.timeslot.day_of_week, c.timeslot.minutes_from_midnight),
            )
            for course in seances:
                cours = ET.SubElement(rattaches, "COURS")
                _texte(cours, "CODE_ALTERNANCE", course.alternation.code)
                _texte(cours, "JOUR", course.timeslot.day_of_week)
                _texte(cours, "HEURE_DEBUT", _hhmm(course.timeslot.minutes_from_midnight))
                _texte(cours, "DUREE", _hhmm(course.duration_minutes))
        if len(bloc):
            noeud.append(service)

    if len(noeud):
        return True
    parent.remove(noeud)
    return False


def _divisions_du_groupe(group) -> list:
    """
    Divisions auxquelles un groupe emprunte ses élèves, lues par ses parties de classe : le modèle
    n'a pas de lien direct groupe → division, la partition en porte un vers sa division.
    Leur nombre dit à lui seul la nature du groupe côté STS — une seule division en fait un
    groupe, plusieurs un regroupement.
    """
    return sorted({
        cp.partition.division.code
        for cp in group.class_parts
        if cp.partition and cp.partition.division
    })


def _ajouter_structure(racine, par_structure: dict):
    donnees = ET.SubElement(racine, "DONNEES")
    structure = ET.SubElement(donnees, "STRUCTURE")

    # L'ordre des enfants n'est pas libre : SERVICES puis MEFS_APPARTENANCE sous DIVISION,
    # LIBELLE_LONG puis DIVISIONS_APPARTENANCE puis SERVICES sous GROUPE. Il est repris du fichier
    # descendant, où il est prouvé, et le schéma l'impose (séquences, pas un choix libre).
    divisions = {k: v for k, v in par_structure.items() if k[0] == "division"}
    if divisions:
        noeud = ET.SubElement(structure, "DIVISIONS")
        for entree in sorted(divisions.values(), key=lambda e: e["structure"].code):
            division = entree["structure"]
            element = ET.SubElement(noeud, "DIVISION", {"CODE": division.code})
            if not _ajouter_services(element, entree["services"]):
                noeud.remove(element)
                continue
            mefs = sorted(
                (lien.mef for lien in division.mef_links if lien.mef),
                key=lambda m: m.code_national,
            )
            if mefs:
                appartenance = ET.SubElement(element, "MEFS_APPARTENANCE")
                for mef in mefs:
                    ET.SubElement(appartenance, "MEF", {"CODE": mef.code_national})
        if not len(noeud):
            structure.remove(noeud)

    groupes = {k: v for k, v in par_structure.items() if k[0] == "group"}
    if groupes:
        noeud = ET.SubElement(structure, "GROUPES")
        for entree in sorted(groupes.values(), key=lambda e: e["structure"].name):
            group = entree["structure"]
            codes = _divisions_du_groupe(group)
            if not codes:
                continue  # groupe sans division d'appartenance : signalé bloquant par l'audit
            element = ET.SubElement(noeud, "GROUPE", {"CODE": group.name})
            # `name` est contraint à 8 caractères parce qu'il EST le code STS : sans ce libellé,
            # le groupe arriverait à l'académie sous sa seule abréviation.
            if group.long_name:
                _texte(element, "LIBELLE_LONG", group.long_name)
            appartenance = ET.SubElement(element, "DIVISIONS_APPARTENANCE")
            for code in codes:
                ET.SubElement(appartenance, "DIVISION_APPARTENANCE", {"CODE": code})
            if not _ajouter_services(element, entree["services"]):
                noeud.remove(element)
        if not len(noeud):
            structure.remove(noeud)


def validate_against_schema(contenu: str):
    """
    Valide le document contre `schemas/emp_sts.xsd`. Filet de sécurité de dernier ressort : un
    document invalide signale un défaut de CE module, pas une donnée mal saisie — les erreurs de
    données, elles, sont attrapées bien avant par l'audit. Mieux vaut refuser de produire que
    transmettre un fichier douteux à l'académie.
    """
    import xmlschema

    schema = xmlschema.XMLSchema(str(SCHEMA_PATH))
    try:
        schema.validate(contenu)
    except xmlschema.XMLSchemaValidationError as exc:
        raise StsExportError(
            "Le fichier de remontée produit ne respecte pas le schéma attendu — c'est une anomalie "
            f"interne, aucun fichier n'a été transmis. Détail : {exc}"
        ) from exc


def build_emp_sts(db, school, validate: bool = True) -> str:
    """Sérialise la remontée d'un établissement et renvoie le contenu XML."""
    par_structure, alternances = _collecter(db, school)

    racine = ET.Element(ROOT_TAG)
    _ajouter_alternances(racine, alternances)
    _ajouter_structure(racine, par_structure)
    ET.indent(racine, space="  ")

    corps = ET.tostring(racine, encoding="unicode")
    contenu = f'<?xml version="1.0" encoding="UTF-8"?>\n<!--{EN_TETE}-->\n{corps}\n'
    if validate:
        validate_against_schema(contenu)
    return contenu


def export_filename(school, school_year: int) -> str:
    """`emp_sts_<RNE>_<ANNEE>.xml` — nom exact attendu, validé par regex chez CDT_6000."""
    return f"emp_sts_{school.uai}_{school_year}.xml"

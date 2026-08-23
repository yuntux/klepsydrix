"""
Génération du flux montant élèves/groupes vers SIECLE : `<UAJ>_ELEGROUPE_<AAAAMMJJ>.xml`,
racine `IMPORT_ELEVES`.

Sens **montant** uniquement — de Klepsydrix vers SIECLE. Format reconstitué à partir de GEPI (voir
le dossier d'analyse XML_STS_SCONET/xsd_et_norme/ExportGroupesSconet.xsd), avec deux écarts
assumés — documentés en détail dans schemas/import_eleves.xsd — plutôt qu'une copie fidèle du
comportement de GEPI :
- `CODE_GROUPE` porte le code structurel SIECLE réel (`Group.name`), pas un identifiant interne ;
- `DATE_DEBUT_GROUPE` porte la date réelle du rattachement (`StudentClassPartLink.begin_date`),
  pas une borne globale d'établissement.

Seuls les rattachements ACTIFS (`StudentClassPartLink.end_date IS NULL`) sont exportés : leur date
de fin réelle n'est par construction pas encore connue, `DATE_FIN_GROUPE` retombe donc sur la date
de sortie des élèves de l'établissement (`School.student_end_date`), qui doit être renseignée.

Un élève n'est exportable que s'il porte un `siecle_id` (jamais importé depuis SIECLE, il n'y
existe pas) et une `birth_date` (`DATE_NAISS` est un champ obligatoire du format). Les deux motifs
d'exclusion sont calculés par `eligible_and_excluded_students`, seule source de vérité partagée
entre l'aperçu du wizard et la génération réelle — pour qu'ils ne puissent jamais diverger.

Module **pur** : lit la base, renvoie une chaîne XML. N'écrit rien, n'incrémente pas le compteur
NUM_ENVOI (fait par le wizard, une fois le fichier réellement généré).
"""
import pathlib
from datetime import date as _date
from xml.etree import ElementTree as ET

ROOT_TAG = "IMPORT_ELEVES"
VERSION = "1.3"
LOGICIEL = "KLEPSYDRIX"
SCHEMA_PATH = pathlib.Path(__file__).parent / "schemas" / "import_eleves.xsd"


class ElevesExportError(RuntimeError):
    """Le document produit ne respecte pas le schéma, ou l'établissement n'est pas configuré pour
    cet export. Message destiné à l'utilisateur (date de sortie manquante) ou au développeur
    (schéma non respecté)."""


def _texte(parent, tag: str, valeur):
    noeud = ET.SubElement(parent, tag)
    noeud.text = "" if valeur is None else str(valeur)
    return noeud


def _groupes_actifs(student) -> list:
    """
    Une entrée (Group, StudentClassPartLink) par groupe auquel l'élève appartient ACTUELLEMENT —
    une ClassPart active qui n'appartient à aucun Group (simple découpage interne, jamais nommé
    côté STS) ne produit aucune ligne : elle n'a pas de CODE_GROUPE à exporter.
    """
    lignes = []
    for lien in student.class_part_links:
        if lien.end_date is not None:
            continue
        for group in lien.class_part.groups:
            lignes.append((group, lien))
    return lignes


def eligible_and_excluded_students(db, school) -> tuple:
    """
    Partage la même logique entre l'aperçu (lecture seule) et la génération réelle.
    Renvoie (eligibles, exclus) : `eligibles` une liste de (Student, nombre_de_groupes),
    `exclus` une liste de (Student, motif).
    """
    from backend.app.models.student import Student
    from backend.app.models.division import Division

    candidats = (
        db.query(Student)
        .join(Division, Student.division_id == Division.id)
        .filter(Division.school_id == school.id)
        .order_by(Student.last_name, Student.first_name)
        .all()
    )
    eligibles, exclus = [], []
    for student in candidats:
        if not student.siecle_id:
            exclus.append((student, "jamais importé depuis SIECLE (aucun identifiant SIECLE connu)"))
            continue
        if not student.birth_date:
            exclus.append((student, "date de naissance inconnue"))
            continue
        eligibles.append((student, len(_groupes_actifs(student))))
    return eligibles, exclus


def validate_against_schema(contenu: str):
    """Filet de sécurité de dernier ressort : un document invalide signale un défaut de CE
    module, pas une donnée mal saisie."""
    import xmlschema

    schema = xmlschema.XMLSchema(str(SCHEMA_PATH))
    try:
        schema.validate(contenu)
    except xmlschema.XMLSchemaValidationError as exc:
        raise ElevesExportError(
            "Le fichier produit ne respecte pas le schéma attendu — c'est une anomalie interne, "
            f"aucun fichier n'a été transmis. Détail : {exc}"
        ) from exc


def build_import_eleves(db, school, date_export: _date, num_envoi: int, validate: bool = True) -> str:
    """Sérialise l'export d'un établissement et renvoie le contenu XML."""
    from backend.app.models.system_setting import SystemSetting

    if not school.student_end_date:
        raise ElevesExportError(
            "La date de sortie des élèves n'est pas renseignée sur la fiche établissement "
            "— indispensable pour DATE_FIN_GROUPE. Complétez-la (fiche Établissement, "
            "rubrique Rentrée) avant de générer ce fichier."
        )

    eligibles, _ = eligible_and_excluded_students(db, school)

    racine = ET.Element(ROOT_TAG, {"VERSION": VERSION})
    parametres = ET.SubElement(racine, "PARAMETRES")
    _texte(parametres, "UAJ", school.uai)
    _texte(parametres, "ANNEE_SCOLAIRE", SystemSetting.get_school_year(db))
    _texte(parametres, "DATE_IMPORT", date_export.strftime("%d/%m/%Y"))
    _texte(parametres, "NUM_ENVOI", str(num_envoi))
    _texte(parametres, "LOGICIEL", LOGICIEL)

    donnees = ET.SubElement(racine, "DONNEES")
    eleves_noeud = ET.SubElement(donnees, "ELEVES")
    for student, _n in eligibles:
        eleve = ET.SubElement(eleves_noeud, "ELEVE")
        _texte(eleve, "ELEVE_ID", student.siecle_id)
        _texte(eleve, "NOM", student.last_name)
        _texte(eleve, "PRENOM", student.first_name)
        _texte(eleve, "DATE_NAISS", student.birth_date.isoformat())
        groupes_noeud = ET.SubElement(eleve, "GROUPES")
        for group, lien in _groupes_actifs(student):
            groupe_noeud = ET.SubElement(groupes_noeud, "GROUPE")
            _texte(groupe_noeud, "CODE_GROUPE", group.name)
            _texte(groupe_noeud, "DATE_DEBUT_GROUPE", lien.begin_date.isoformat())
            _texte(groupe_noeud, "DATE_FIN_GROUPE", school.student_end_date.isoformat())

    ET.indent(racine, space="  ")
    corps = ET.tostring(racine, encoding="unicode")
    contenu = f'<?xml version="1.0" encoding="UTF-8"?>\n{corps}\n'
    if validate:
        validate_against_schema(contenu)
    return contenu


def export_filename(school, date_export: _date) -> str:
    """`<UAJ>_ELEGROUPE_<AAAAMMJJ>.xml` — convention documentée dans
    XML_STS_SCONET/xsd_et_norme/FORMATS_JUSTIFICATION.md §11.7 (GEPI, lui, produit un nom non
    déterministe, `export_groupes_<horodatage>_<aléa>.xml`)."""
    return f"{school.uai}_ELEGROUPE_{date_export:%Y%m%d}.xml"

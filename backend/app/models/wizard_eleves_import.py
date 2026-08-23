"""
Wizard « Importer les élèves et responsables SIECLE » — deux fichiers XML (ou .zip contenant un
XML), ElevesAvecAdresses.xml et ResponsablesAvecAdresses.xml, sens descendant uniquement. Même
patron que wizard_sts_import.py : contrôles bloquants d'abord, aperçu ensuite, écriture à la fin
seulement — mais en trois étapes et non quatre, faute de résolution d'identifiant à soumettre à
l'utilisateur (voir plus bas, tout est soit résolu dynamiquement, soit bloquant).

**Les deux fichiers sont OBLIGATOIRES** (`required` sur les deux champs binaires de l'étape 1, ET
contrôlé côté serveur dans `_load()` — un appel API qui contournerait le formulaire est refusé de
la même façon). C'est ce qui rend fiable le rattachement des responsables aux bons élèves :
`RESPONSABLE/ELEVE_ID` est un identifiant interne à l'export SIECLE du jour — rien ne garantit
qu'il reste stable d'un export à l'autre, et Klepsydrix ne le conserve nulle part (voir
Student.national_id, qui porte ID_NATIONAL, une valeur différente). La correspondance
ELEVE_ID -> élève n'est donc construite qu'en mémoire, à partir du fichier élèves déposé dans LE
MÊME import.

**Trois garde-fous avant toute écriture**, comme pour STS-web plus la présence des deux fichiers :
l'année de chaque fichier doit être celle de la base, le RNE doit être celui d'un établissement de
la base, et les deux fichiers doivent porter le même RNE et la même année l'un que l'autre.

**Politique de résolution, décidée explicitement plutôt que par défaut** :
- Division : créée dynamiquement si son code est inconnu (aucun libellé dans ce fichier, le code
  sert de nom provisoire).
- MEF : jamais créé ex nihilo (le fichier ne porte qu'un code, sans libellé ni niveau) — un élève
  dont le MEF est inconnu de la base est laissé de côté. Si le MEF existe mais n'est pas encore
  rattaché à la division de l'élève, le rattachement (MefDivision) est créé à la volée.
- Groupes (répartition dans les groupes, `import_groups`, décoché par défaut) : le groupe est créé
  dynamiquement si nécessaire, avec une partition/partie de classe pour la division de l'élève. Si
  l'élève n'a de division ni dans ce fichier ni déjà en base, ET que le groupe n'existe pas encore,
  le groupe n'est pas créé et l'élève est signalé dans le bilan.
- Options/spécialités (OPTIONS_ELEVE) : la matière et la modalité d'élection doivent déjà exister
  en base, sans quoi la ligne est bloquante et laissée de côté — voir StudentSpecialtyChoice.
- Régime, civilité, responsabilité légale : nomenclatures fermées et seedées (RefRegime, RefTitle,
  RefLegalGuardian) — une valeur non reconnue est laissée vide, jamais inventée.
- Motif de sortie, profession, lien de parenté, établissement d'origine : nomenclatures ouvertes,
  créées dynamiquement à la première rencontre d'un code inconnu (RefExitReason, RefJob,
  RefRelativeLink, RefExternalSchool).

**Clé d'appariement** : `Student.national_id` (ID_NATIONAL) pour les élèves, `Parent.siecle_id`
(PERSONNE_ID) pour les responsables — les deux posés en lecture seule (voir student.py/parent.py),
jamais modifiables à la main.
"""
import base64
from datetime import date as _date

from sqlalchemy.orm import Session

from backend.app.core.eleves_flux import ElevesFluxError, parse_eleves, parse_responsables
from backend.app.core.zip_xml import extract_xml
from backend.app.core.upload_limits import assert_within_limit
from backend.app.core.ref_lookup import find_or_create_ref
from backend.app.core.sts_naming import validate_sts_group_name
from backend.app.core.html_text import esc
from backend.app.models.base import TransientModel, requires_access
from backend.app.models.gender import GENDER_FROM_STS
from backend.app.models.division import Division
from backend.app.models.group import Group, Partition, ClassPart, _partition_code
from backend.app.models.mef import Mef, MefDivision
from backend.app.models.parent import Parent
from backend.app.models.ref_city import RefCity
from backend.app.models.ref_country import RefCountry
from backend.app.models.ref_exit_reason import RefExitReason
from backend.app.models.ref_external_school import RefExternalSchool
from backend.app.models.ref_election_method import RefElectionMethod
from backend.app.models.ref_job import RefJob
from backend.app.models.ref_legal_guardian import RefLegalGuardian
from backend.app.models.ref_regime import RefRegime
from backend.app.models.ref_relative_link import RefRelativeLink
from backend.app.models.ref_title import RefTitle
from backend.app.models.school import School
from backend.app.models.student import Student, StudentParentLink, StudentSpecialtyChoice, StudentClassPartLink
from backend.app.models.subject import Subject
from backend.app.models.system_setting import SystemSetting

ENTITY_LABELS = [
    ("students", "Élèves (identité et scolarité)"),
    ("groups", "Répartition dans les groupes"),
    ("options", "Vœux de spécialité et options"),
    ("persons", "Responsables (identité et coordonnées)"),
    ("links", "Rattachement élèves ↔ responsables"),
]

MISSING_DISPLAY_LIMIT = 20

EXPERIMENTAL_NOTICE = (
    '<div style="border-left:4px solid #3B82F6;background:#EFF6FF;padding:12px 16px;'
    'border-radius:4px;margin-bottom:16px;">'
    "<p><strong>Fonction expérimentale.</strong> Le ministère de l'éducation nationale ne publie pas "
    "sur son site public les normes d'échange SIECLE, et l'auteur ne dispose d'aucun fichier "
    "d'exemple réel. La structure des fichiers a été déduite du code d'import de "
    "<strong>GEPI</strong> ; elle est probablement incomplète.</p>"
    "<p>Déposez <strong>les deux fichiers</strong> <code>ElevesAvecAdresses.xml</code> et "
    "<code>ResponsablesAvecAdresses.xml</code>, obtenus depuis SIECLE par <em>Exploitation &gt; "
    "Exports standard &gt; Exports XML générique</em>, seuls ou dans un .zip. "
    "<strong>Les deux sont obligatoires</strong> : c'est ce qui permet de rattacher chaque "
    "responsable au bon élève — voir la remarque en tête de "
    "<code>wizard_eleves_import.py</code>.</p>"
    "<p>Si vous disposez des spécifications officielles, ou d'exemples de fichiers "
    "pseudonymisés, n'hésitez pas à me les envoyer.</p>"
    "</div>"
)


def _decode_upload(file_field, filename_hint: str, label: str):
    if not file_field:
        return None
    if isinstance(file_field, (bytes, bytearray)):
        data = assert_within_limit(bytes(file_field), label)
    elif isinstance(file_field, str):
        data = assert_within_limit(base64.b64decode(file_field), label)
    else:
        raw = (file_field or {}).get("data_base64")
        if not raw:
            raise ValueError(f"{label} : le fichier fourni est vide ou illisible.")
        data = assert_within_limit(base64.b64decode(raw), label)
    return extract_xml(data, filename_hint, label)


def _resolve_school(db: Session, uai: str) -> School:
    school = db.query(School).filter(School.uai == uai).first()
    if not school:
        connus = ", ".join(s.uai for s in db.query(School).order_by(School.uai).all()) or "aucun"
        raise ValueError(
            f"Le RNE {uai} de ce fichier ne correspond à aucun établissement de la base (RNE "
            f"connus : {connus}). Créez l'établissement au préalable, ou importez le fichier du "
            f"bon RNE."
        )
    return school


def _load(db: Session, students_file, parents_file):
    """
    Parse les DEUX fichiers + contrôles bloquants. N'écrit rien.

    Les deux sont obligatoires — pas seulement côté widget (`required` sur students_file et
    parents_file, voir __actions__) mais aussi ici : un appel API qui contournerait le formulaire
    doit être refusé de la même façon. C'est également ce qui rend fiable la correspondance
    RESPONSABLE/ELEVE_ID -> élève, construite en mémoire à partir du seul fichier élèves déposé
    dans CET import (voir docstring du module).
    """
    if not students_file:
        raise ValueError("Le fichier élèves (ElevesAvecAdresses) est obligatoire.")
    if not parents_file:
        raise ValueError("Le fichier responsables (ResponsablesAvecAdresses) est obligatoire.")

    try:
        students_flux = parse_eleves(_decode_upload(students_file, "Eleves", "Le fichier élèves"))
        parents_flux = parse_responsables(_decode_upload(parents_file, "Responsables", "Le fichier responsables"))
    except ElevesFluxError as exc:
        raise ValueError(str(exc)) from exc

    expected_year = SystemSetting.get_school_year(db)
    for flux, label in ((students_flux, "élèves"), (parents_flux, "responsables")):
        if flux.school_year != expected_year:
            raise ValueError(
                f"Le fichier {label} porte l'année scolaire {flux.school_year}-{flux.school_year + 1} "
                f"alors que cette base est celle de {expected_year}-{expected_year + 1}."
            )
    if students_flux.uai != parents_flux.uai:
        raise ValueError(
            f"Le fichier élèves porte le RNE {students_flux.uai}, le fichier responsables le RNE "
            f"{parents_flux.uai} — déposez deux exports du même établissement."
        )

    school = _resolve_school(db, students_flux.uai)
    return students_flux, parents_flux, school


def _parse_date_fr(value):
    """SIECLE : dates au format JJ/MM/AAAA (DateFRType), à ne pas confondre avec le AAAA-MM-JJ de
    STS-web (voir wizard_sts_import._parse_date)."""
    if not value:
        return None
    try:
        jour, mois, annee = str(value).strip()[:10].split("/")
        return _date(int(annee), int(mois), int(jour))
    except (ValueError, TypeError):
        return None


def _bool01(value) -> bool:
    return (value or "").strip() == "1"


# --------------------------------------------------------------------------------------------
#  Aperçu : lecture seule, aucune écriture
# --------------------------------------------------------------------------------------------

def _build_plan(db: Session, students_flux, parents_flux, school: School, selection: dict) -> dict:
    plan = {key: {"create": [], "update": [], "skipped": []} for key, _ in ENTITY_LABELS}

    resolved_students = {}  # eleve_id (fichier) -> Student existant ou None si à créer/skip
    if students_flux and selection.get("students"):
        for eleve in students_flux.students:
            libelle = f"{eleve['first_name'] or ''} {eleve['last_name'] or ''}".strip() or eleve["eleve_id"]
            existing = None
            if eleve["id_national"]:
                existing = db.query(Student).filter(Student.national_id == eleve["id_national"]).first()
            if existing:
                plan["students"]["update"].append({"code": eleve["eleve_id"], "label": libelle})
                continue
            division = db.query(Division).filter(Division.code == eleve["division_code"]).first() if eleve["division_code"] else None
            if not eleve["division_code"]:
                plan["students"]["skipped"].append({
                    "code": eleve["eleve_id"], "label": libelle,
                    "reason": "aucune division dans le fichier (STRUCTURE de type D) — impossible de créer l'élève",
                })
                continue
            mef = db.query(Mef).filter(Mef.code_national == eleve["mef_code"]).first() if eleve["mef_code"] else None
            if not mef:
                plan["students"]["skipped"].append({
                    "code": eleve["eleve_id"], "label": libelle,
                    "reason": f"le MEF « {eleve['mef_code']} » n'existe pas dans la base (le fichier ne porte pas de quoi le créer)",
                })
                continue
            plan["students"]["create"].append({"code": eleve["eleve_id"], "label": libelle})

    if students_flux and selection.get("groups"):
        for eleve in students_flux.students:
            if not eleve["group_codes"]:
                continue
            libelle = f"{eleve['first_name'] or ''} {eleve['last_name'] or ''}".strip() or eleve["eleve_id"]
            existing = db.query(Student).filter(Student.national_id == eleve["id_national"]).first() if eleve["id_national"] else None
            has_division = bool(eleve["division_code"]) or bool(existing and existing.division_id)
            for code in eleve["group_codes"]:
                group_exists = db.query(Group).filter(Group.name == code).first()
                if not has_division and not group_exists:
                    plan["groups"]["skipped"].append({
                        "code": code, "label": f"{libelle} -> {code}",
                        "reason": "élève sans division (ni dans le fichier, ni en base) et groupe inexistant : le groupe n'est pas créé",
                    })
                    continue
                if not has_division:
                    plan["groups"]["skipped"].append({
                        "code": code, "label": f"{libelle} -> {code}",
                        "reason": "élève sans division (ni dans le fichier, ni en base) : impossible de l'y rattacher",
                    })
                    continue
                (plan["groups"]["update"] if group_exists else plan["groups"]["create"]).append(
                    {"code": code, "label": f"{libelle} -> {code}"}
                )

    if students_flux and selection.get("options"):
        for eleve in students_flux.students:
            libelle = f"{eleve['first_name'] or ''} {eleve['last_name'] or ''}".strip() or eleve["eleve_id"]
            for option in eleve["options"]:
                repere = f"{libelle} -> {option['subject_code']}"
                subject = db.query(Subject).filter(Subject.code_nomenclature == option["subject_code"]).first()
                if not subject:
                    plan["options"]["skipped"].append({
                        "code": repere, "label": repere,
                        "reason": f"la matière « {option['subject_code']} » n'existe pas dans la base",
                    })
                    continue
                methode = db.query(RefElectionMethod).filter(RefElectionMethod.code == option["election_code"]).first() if option["election_code"] else None
                if option["election_code"] and not methode:
                    plan["options"]["skipped"].append({
                        "code": repere, "label": repere,
                        "reason": f"la modalité d'élection « {option['election_code']} » n'existe pas dans la base",
                    })
                    continue
                plan["options"]["create"].append({"code": repere, "label": repere})

    if parents_flux and selection.get("persons"):
        for personne_id, personne in parents_flux.persons.items():
            libelle = f"{personne['first_name'] or ''} {personne['last_name'] or ''}".strip() or personne_id
            cible = "update" if db.query(Parent).filter(Parent.siecle_id == personne_id).first() else "create"
            plan["persons"][cible].append({"code": personne_id, "label": libelle})

    if parents_flux and selection.get("links"):
        # `students_flux` est garanti non nul ici (les deux fichiers sont obligatoires, voir
        # _load) : eleve_ids_connus couvre donc toujours le fichier élèves déposé dans cet import.
        eleve_ids_connus = {e["eleve_id"] for e in students_flux.students}
        for link in parents_flux.links:
            personne = parents_flux.persons.get(link["personne_id"])
            libelle_personne = (
                f"{personne['first_name'] or ''} {personne['last_name'] or ''}".strip()
                if personne else link["personne_id"]
            )
            repere = f"{libelle_personne} -> élève {link['eleve_id']}"
            if link["eleve_id"] not in eleve_ids_connus:
                plan["links"]["skipped"].append({
                    "code": repere, "label": repere,
                    "reason": f"aucun élève d'identifiant fichier « {link['eleve_id']} » dans le fichier élèves déposé",
                })
                continue
            plan["links"]["create"].append({"code": repere, "label": repere})

    return plan


def _summary_rows(plan: dict) -> list:
    return [
        {
            "entity": libelle,
            "to_create": len(plan[key]["create"]),
            "to_update": len(plan[key]["update"]),
            "skipped": len(plan[key]["skipped"]),
        }
        for key, libelle in ENTITY_LABELS
    ]


def _skipped_html(plan: dict) -> str:
    lignes = []
    for key, libelle in ENTITY_LABELS:
        elements = plan[key]["skipped"]
        if not elements:
            continue
        lignes.append(f"<li><strong>{esc(libelle)}</strong> — {len(elements)} objet(s) :<ul>")
        for e in elements[:MISSING_DISPLAY_LIMIT]:
            lignes.append(f"<li>« {esc(e['label'])} » : {esc(e['reason'])}</li>")
        reste = len(elements) - min(len(elements), MISSING_DISPLAY_LIMIT)
        if reste:
            lignes.append(f"<li>… et {reste} autre(s), pour la même raison ou une raison voisine</li>")
        lignes.append("</ul></li>")
    if not lignes:
        return "<p>Aucun objet laissé de côté.</p>"
    return f"<p><strong>Objets laissés de côté</strong> — ils ne seront ni créés ni modifiés :</p><ul>{''.join(lignes)}</ul>"


def _header_html(students_flux, parents_flux, school: School) -> str:
    lignes = [f"<p><strong>{esc(school.name)}</strong> — RNE {esc(school.uai)}.</p>"]
    for flux, label in ((students_flux, "élèves"), (parents_flux, "responsables")):
        if not flux:
            lignes.append(f"<p>Fichier {label} : non déposé.</p>")
            continue
        date_export = flux.date_export or "non renseignée"
        horodatage = flux.horodatage or "non renseigné"
        lignes.append(
            f"<p>Fichier {label} — export du <strong>{esc(date_export)}</strong> "
            f"(horodatage {esc(horodatage)}). Ces deux informations ne sont pas conservées en "
            f"base : elles ne servent qu'à distinguer deux exports faits à des dates "
            f"différentes.</p>"
        )
    if students_flux and parents_flux and (students_flux.date_export, students_flux.horodatage) != (parents_flux.date_export, parents_flux.horodatage):
        lignes.append(
            "<p style=\"color:#B45309\">Les deux fichiers n'ont pas la même date d'export : "
            "vérifiez qu'ils proviennent bien de la même session avant de poursuivre — "
            "RESPONSABLE/ELEVE_ID n'est fiable qu'entre deux fichiers exportés ensemble.</p>"
        )
    return "".join(lignes)


# --------------------------------------------------------------------------------------------
#  Écriture — appelé uniquement par rpc_import
# --------------------------------------------------------------------------------------------

def _find_or_create_city_by_insee(db: Session, insee_code, name=None):
    insee_code = (insee_code or "").strip()
    if not insee_code:
        return None
    city = db.query(RefCity).filter(RefCity.insee_code == insee_code).first()
    if city:
        return city.id
    return RefCity.create(db, {"name": (name or insee_code)[:100], "insee_code": insee_code[:5]}).id


def _find_or_create_country(db: Session, name):
    name = (name or "").strip()
    if not name:
        return None
    country = db.query(RefCountry).filter(RefCountry.name == name[:100]).first()
    if country:
        return country.id
    return RefCountry.create(db, {"name": name[:100]}).id


def _find_or_create_city_by_name_zip(db: Session, name, zip_code, country_id=None):
    name = (name or "").strip()
    if not name:
        return None
    zip_code = (zip_code or None) and zip_code[:20]
    city = db.query(RefCity).filter(RefCity.name == name[:100], RefCity.zip_code == zip_code).first()
    if city:
        return city.id
    vals = {"name": name[:100], "zip_code": zip_code}
    if country_id:
        vals["country_id"] = country_id
    return RefCity.create(db, vals).id


def _find_or_create_external_school(db: Session, last_year: dict):
    rne_code = (last_year.get("rne_code") or "").strip() or None
    name = (last_year.get("denom_princ") or "").strip() or None
    if not (rne_code or name):
        return None
    query = db.query(RefExternalSchool)
    existing = query.filter(RefExternalSchool.rne_code == rne_code).first() if rne_code else None
    if not existing and name:
        existing = query.filter(RefExternalSchool.name == name[:200]).first()
    city_id = _find_or_create_city_by_insee(db, last_year.get("city_insee_code"), last_year.get("city_name"))
    vals = {
        "long_name": (last_year.get("denom_compl") or None) and last_year["denom_compl"][:200],
        "sigle": (last_year.get("sigle") or None) and last_year["sigle"][:20],
        "address_line1": (last_year.get("address_line1") or None) and last_year["address_line1"][:150],
        "address_line2": (last_year.get("address_line2") or None) and last_year["address_line2"][:150],
        "address_line3": (last_year.get("address_line3") or None) and last_year["address_line3"][:150],
        "address_line4": (last_year.get("address_line4") or None) and last_year["address_line4"][:150],
        "po_box": (last_year.get("po_box") or None) and last_year["po_box"][:50],
        "email": (last_year.get("email") or None) and last_year["email"][:150],
        "phone": (last_year.get("phone") or None) and last_year["phone"][:20],
        "city_id": city_id,
    }
    vals = {k: v for k, v in vals.items() if v is not None}
    if existing:
        existing.update(db, vals)
        return existing.id
    vals["name"] = (name or rne_code)[:200]
    if rne_code:
        vals["rne_code"] = rne_code
    return RefExternalSchool.create(db, vals).id


def _apply_students(db: Session, students_flux, school: School, selection: dict, plan: dict) -> tuple:
    """Retourne (students_par_eleve_id, compteurs, mefs_rattaches_dynamiquement)."""
    students_par_eleve_id = {}
    compteurs = {"created": 0, "updated": 0}
    mefs_rattaches = 0
    if not (students_flux and selection.get("students")):
        return students_par_eleve_id, compteurs, mefs_rattaches

    a_creer = {e["code"] for e in plan["students"]["create"]}
    a_maj = {e["code"] for e in plan["students"]["update"]}

    for eleve in students_flux.students:
        if eleve["eleve_id"] not in a_creer and eleve["eleve_id"] not in a_maj:
            continue

        division = None
        if eleve["division_code"]:
            division = db.query(Division).filter(Division.code == eleve["division_code"]).first()
            if not division:
                division = Division.create(db, {
                    "code": eleve["division_code"][:30], "name": eleve["division_code"][:50],
                    "school_id": school.id,
                })

        mef = db.query(Mef).filter(Mef.code_national == eleve["mef_code"]).first() if eleve["mef_code"] else None
        regime = db.query(RefRegime).filter(RefRegime.code == eleve["regime_code"]).first() if eleve["regime_code"] else None

        vals = {
            "first_name": (eleve["first_name"] or "")[:50],
            "last_name": (eleve["last_name"] or "")[:50],
            "birth_last_name": (eleve["birth_last_name"] or None) and eleve["birth_last_name"][:50],
            "gender": GENDER_FROM_STS.get((eleve["sexe"] or "").strip()),
            "birth_date": _parse_date_fr(eleve["birth_date"]),
            "birth_city_id": _find_or_create_city_by_insee(db, eleve["birth_city_insee_code"]),
            "doublement": _bool01(eleve["doublement"]),
            "entry_date": _parse_date_fr(eleve["entry_date"]),
            "exit_date": _parse_date_fr(eleve["exit_date"]),
            "exit_reason_id": find_or_create_ref(db, RefExitReason, eleve["exit_reason_code"]),
            "regime_id": regime.id if regime else None,
            "last_year_level": (eleve["last_year"] or {}).get("level") if eleve["last_year"] else None,
            "last_year_school_id": _find_or_create_external_school(db, eleve["last_year"]) if eleve["last_year"] else None,
            "national_id": eleve["id_national"],
            "ine_bea": eleve["ine_bea"],
            "elenoet": eleve["elenoet"],
            # ELEVE_ID (attribut du fichier) : identifiant PROPRE À CET EXPORT, distinct de
            # national_id — voir student.py. Toujours réécrit à l'identique du fichier, jamais
            # comparé à l'ancienne valeur : rien ne garantit sa stabilité d'un export à l'autre.
            "siecle_id": eleve["eleve_id"],
        }
        vals = {k: v for k, v in vals.items() if v is not None}

        # Le rattachement MEF <-> division doit exister AVANT toute création/mise à jour d'élève :
        # _check_student_mef_matches_division (student.py) l'exige dès la sauvegarde, il ne peut
        # pas être ajouté après coup.
        if mef and division:
            deja_lie = db.query(MefDivision).filter(
                MefDivision.mef_id == mef.id, MefDivision.division_id == division.id
            ).first()
            if not deja_lie:
                MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id})
                mefs_rattaches += 1

        existing = db.query(Student).filter(Student.national_id == eleve["id_national"]).first() if eleve["id_national"] else None
        if existing:
            existing.update(db, vals)
            student = existing
            compteurs["updated"] += 1
        else:
            if not division:
                continue  # déjà signalé dans le plan (students/skipped)
            if not mef:
                continue  # idem
            vals["division_id"] = division.id
            vals["mef_id"] = mef.id
            student = Student.create(db, vals)
            compteurs["created"] += 1

        students_par_eleve_id[eleve["eleve_id"]] = student

    return students_par_eleve_id, compteurs, mefs_rattaches


def _resolve_student_division(student: Student, eleve: dict, db: Session):
    if eleve["division_code"]:
        return db.query(Division).filter(Division.code == eleve["division_code"]).first()
    return student.division if student else None


def _apply_groups(db: Session, students_flux, students_par_eleve_id: dict, selection: dict, plan: dict) -> dict:
    compteurs = {"created": 0, "updated": 0}
    if not (students_flux and selection.get("groups")):
        return compteurs

    a_creer = {e["code"] for e in plan["groups"]["create"]}
    a_maj = {e["code"] for e in plan["groups"]["update"]}

    for eleve in students_flux.students:
        if not eleve["group_codes"]:
            continue
        student = students_par_eleve_id.get(eleve["eleve_id"]) or (
            db.query(Student).filter(Student.national_id == eleve["id_national"]).first()
            if eleve["id_national"] else None
        )
        for code in eleve["group_codes"]:
            if code not in a_creer and code not in a_maj:
                continue
            division = _resolve_student_division(student, eleve, db)
            if not division:
                continue  # déjà signalé dans le plan (groups/skipped)

            group = db.query(Group).filter(Group.name == code).first()
            if not group:
                try:
                    validate_sts_group_name(code)
                except ValueError:
                    continue  # signalé côté plan si pertinent ; un nom invalide ne peut pas être créé
                group = Group.create(db, {"name": code})
                compteurs["created"] += 1
            else:
                compteurs["updated"] += 1

            code_partition = _partition_code(db, division.id, f"SIECLE_{group.name}")
            partition = db.query(Partition).filter(Partition.code == code_partition).first()
            if not partition:
                partition = Partition.create(db, {
                    "code": code_partition, "name": group.long_name or group.name,
                    "division_id": division.id, "is_system_generated": True,
                })
            class_part = db.query(ClassPart).filter(
                ClassPart.partition_id == partition.id, ClassPart.name == group.name
            ).first()
            if not class_part:
                class_part = ClassPart.create(db, {
                    "partition_id": partition.id, "name": group.name,
                    "is_system_generated": True, "_system_write": True,
                })
            if class_part.id not in {cp.id for cp in group.class_parts}:
                group.update(db, {"class_part_ids": sorted({cp.id for cp in group.class_parts} | {class_part.id})})
            if student and class_part.id not in {cp.id for cp in student.class_parts}:
                # begin_date = date du jour de l'import : le fichier SIECLE ne porte pas la date
                # réelle d'affectation au groupe (voir StudentClassPartLink), seule l'appartenance
                # actuelle. Aucun lien ouvert existant n'est retouché : la contrainte
                # _check_no_two_open_links empêcherait de toute façon un doublon.
                StudentClassPartLink.create(db, {
                    "student_id": student.id, "class_part_id": class_part.id, "begin_date": _date.today(),
                })

    return compteurs


def _apply_options(db: Session, students_flux, students_par_eleve_id: dict, selection: dict, plan: dict) -> dict:
    compteurs = {"created": 0}
    if not (students_flux and selection.get("options")):
        return compteurs

    a_creer = {e["code"] for e in plan["options"]["create"]}
    for eleve in students_flux.students:
        student = students_par_eleve_id.get(eleve["eleve_id"]) or (
            db.query(Student).filter(Student.national_id == eleve["id_national"]).first()
            if eleve["id_national"] else None
        )
        if not student:
            continue
        for option in eleve["options"]:
            libelle = f"{student.first_name} {student.last_name} -> {option['subject_code']}"
            if libelle not in a_creer:
                continue
            subject = db.query(Subject).filter(Subject.code_nomenclature == option["subject_code"]).first()
            methode = db.query(RefElectionMethod).filter(RefElectionMethod.code == option["election_code"]).first() if option["election_code"] else None
            if not subject:
                continue
            deja = db.query(StudentSpecialtyChoice).filter(
                StudentSpecialtyChoice.student_id == student.id, StudentSpecialtyChoice.subject_id == subject.id,
            ).first()
            if deja:
                continue
            rang = int(option["num_option"]) if (option["num_option"] or "").isdigit() else 1
            StudentSpecialtyChoice.create(db, {
                "student_id": student.id, "subject_id": subject.id, "rank": rang,
                "election_method_id": methode.id if methode else None,
            })
            compteurs["created"] += 1
    return compteurs


def _apply_persons(db: Session, parents_flux, selection: dict, plan: dict) -> tuple:
    """Retourne (parents_par_personne_id, compteurs)."""
    parents_par_personne_id = {}
    compteurs = {"created": 0, "updated": 0}
    if not (parents_flux and selection.get("persons")):
        return parents_par_personne_id, compteurs

    a_creer = {e["code"] for e in plan["persons"]["create"]}
    a_maj = {e["code"] for e in plan["persons"]["update"]}

    for personne_id, personne in parents_flux.persons.items():
        if personne_id not in a_creer and personne_id not in a_maj:
            continue
        adresse = parents_flux.addresses.get(personne["adresse_id"]) if personne["adresse_id"] else None
        country_id = _find_or_create_country(db, adresse["country_name"]) if adresse else None
        ville_nom = (adresse.get("foreign_city") if adresse else None) or (adresse.get("postal_label") if adresse else None)
        city_id = _find_or_create_city_by_name_zip(db, ville_nom, adresse.get("zip_code") if adresse else None, country_id) if adresse else None
        titre = db.query(RefTitle).filter(RefTitle.code == (personne["civilite"] or "").strip().upper()).first() if personne["civilite"] else None

        vals = {
            "first_name": (personne["first_name"] or "")[:50],
            "last_name": (personne["last_name"] or "")[:50],
            "birth_last_name": (personne["birth_last_name"] or None) and personne["birth_last_name"][:50],
            "title_id": titre.id if titre else None,
            "job_id": find_or_create_ref(db, RefJob, personne["job_code"]),
            "email": (personne["email"] or None) and personne["email"][:150],
            "mobile_phone": (personne["mobile_phone"] or None) and personne["mobile_phone"][:20],
            "personal_phone": (personne["personal_phone"] or None) and personne["personal_phone"][:20],
            "professional_phone": (personne["professional_phone"] or None) and personne["professional_phone"][:20],
            "accepts_sms": _bool01(personne["accepts_sms"]),
            "communication_by_address": _bool01(personne["communication_by_address"]),
            "address_line1": (adresse.get("address_line1") or None) and adresse["address_line1"][:150] if adresse else None,
            "address_line2": (adresse.get("address_line2") or None) and adresse["address_line2"][:150] if adresse else None,
            "address_line3": (adresse.get("address_line3") or None) and adresse["address_line3"][:150] if adresse else None,
            "address_line4": (adresse.get("address_line4") or None) and adresse["address_line4"][:150] if adresse else None,
            "address_zipcode": (adresse.get("zip_code") or None) and adresse["zip_code"][:20] if adresse else None,
            "address_department_code": (adresse.get("department_code") or None) and adresse["department_code"][:3] if adresse else None,
            "address_city_id": city_id,
            "address_country_id": country_id,
        }
        vals = {k: v for k, v in vals.items() if v is not None}

        existing = db.query(Parent).filter(Parent.siecle_id == personne_id).first()
        if existing:
            existing.update(db, vals)
            compteurs["updated"] += 1
            parents_par_personne_id[personne_id] = existing
        else:
            vals["siecle_id"] = personne_id
            parents_par_personne_id[personne_id] = Parent.create(db, vals)
            compteurs["created"] += 1

    return parents_par_personne_id, compteurs


def _apply_links(db: Session, parents_flux, students_par_eleve_id: dict, parents_par_personne_id: dict, selection: dict, plan: dict) -> dict:
    compteurs = {"created": 0, "updated": 0}
    if not (parents_flux and selection.get("links")):
        return compteurs

    a_traiter = {e["code"] for e in plan["links"]["create"]} | {e["code"] for e in plan["links"]["update"]}

    for link in parents_flux.links:
        personne = parents_flux.persons.get(link["personne_id"])
        libelle_personne = (
            f"{personne['first_name'] or ''} {personne['last_name'] or ''}".strip()
            if personne else link["personne_id"]
        )
        repere = f"{libelle_personne} -> élève {link['eleve_id']}"
        if repere not in a_traiter:
            continue
        student = students_par_eleve_id.get(link["eleve_id"])
        parent = parents_par_personne_id.get(link["personne_id"]) or (
            db.query(Parent).filter(Parent.siecle_id == link["personne_id"]).first()
        )
        if not (student and parent):
            continue

        vals = {
            "relative_link_id": find_or_create_ref(db, RefRelativeLink, link["relative_link_code"]),
            "legal_guardian_id": (
                db.query(RefLegalGuardian).filter(RefLegalGuardian.code == link["resp_legal_code"]).first().id
                if link["resp_legal_code"] and db.query(RefLegalGuardian).filter(RefLegalGuardian.code == link["resp_legal_code"]).first()
                else None
            ),
            "responsibility_level": (link["responsibility_level"] or None) and link["responsibility_level"][:50],
            "pays_school_fees": _bool01(link["pays_school_fees"]),
            "is_financially_responsible": _bool01(link["resp_financier"]),
            "receives_financial_aid": _bool01(link["pers_paiement"]),
            "is_contact": _bool01(link["pers_contact"]),
        }
        vals = {k: v for k, v in vals.items() if v is not None}

        existing = db.query(StudentParentLink).filter(
            StudentParentLink.student_id == student.id, StudentParentLink.parent_id == parent.id,
        ).first()
        if existing:
            existing.update(db, vals)
            compteurs["updated"] += 1
        else:
            vals["student_id"] = student.id
            vals["parent_id"] = parent.id
            StudentParentLink.create(db, vals)
            compteurs["created"] += 1

    return compteurs


# --------------------------------------------------------------------------------------------
#  Wizard
# --------------------------------------------------------------------------------------------

class WizardElevesImport(TransientModel):
    """Enregistrement singleton (id=1 fixe, pas de liste), voir ui.json."""

    __tablename__ = "wizard_eleves_imports"
    _fields = [
        "id", "info_html", "students_file", "parents_file",
        "import_students", "import_groups", "import_options", "import_responsables",
        "header_html", "summary_rows", "skipped_html", "result_html",
    ]
    _field_info = {
        "info_html": {"type": "html", "label": None, "readOnly": True},
        # PAS de clé "required" ici : ce dict alimente json_schema_extra (voir generic.py::
        # make_pydantic_model), où un "required" booléen au niveau d'une PROPRIÉTÉ fait planter la
        # génération d'OpenAPI (JSON-Schema attend une liste, au niveau de l'objet PARENT — même
        # piège que documenté dans teacher.py pour required_field). Le "required": True qui compte
        # réellement pour bloquer la soumission est celui de steps[].fields[] ci-dessous, lu par
        # GenericForm.vue, pas par make_pydantic_model.
        "students_file": {"label": "Fichier élèves (ElevesAvecAdresses)", "type": "binary"},
        "parents_file": {"label": "Fichier responsables (ResponsablesAvecAdresses)", "type": "binary"},
        "header_html": {"type": "html", "label": None, "readOnly": True},
        "summary_rows": {"label": "Contenu du fichier", "type": "text", "widget": "list_preview", "readOnly": True},
        "skipped_html": {"type": "html", "label": None, "readOnly": True},
        "result_html": {"type": "html", "label": None, "readOnly": True},
    }

    _SELECTION_PARAMS = {
        "import_students": "import_students", "import_groups": "import_groups",
        "import_options": "import_options", "import_responsables": "import_responsables",
    }

    __actions__ = [{
        "id": "import_eleves_flux",
        "label": "Importer les élèves et responsables",
        "type": "wizard",
        "steps": [
            {
                "id": "upload",
                "title": "1. Fichiers et contenu à importer",
                "fields": [
                    {"key": "info_html", "type": "html", "label": None},
                    {"key": "students_file", "label": "Fichier élèves (ElevesAvecAdresses)", "type": "binary", "required": True},
                    {"key": "parents_file", "label": "Fichier responsables (ResponsablesAvecAdresses)", "type": "binary", "required": True},
                    {
                        "type": "group",
                        "string": "Périmètre de l'import",
                        "children": [
                            {"key": "import_students", "label": "Importer les élèves (identité et scolarité)", "type": "boolean"},
                            {"key": "import_groups", "label": "Importer la répartition des élèves dans les groupes", "type": "boolean"},
                            {"key": "import_options", "label": "Importer les vœux de spécialité et options", "type": "boolean"},
                            {"key": "import_responsables", "label": "Importer les responsables (identité, coordonnées, rattachement)", "type": "boolean"},
                        ],
                    },
                ],
                "submitLabel": "Analyser",
                "rpc": "rpc_analyze",
                "rpcParams": {"students_file": "students_file", "parents_file": "parents_file", **_SELECTION_PARAMS},
            },
            {
                "id": "review",
                "title": "2. Aperçu",
                "fields": [
                    {"key": "header_html", "type": "html", "label": None},
                    {
                        "key": "summary_rows", "label": "Contenu du fichier", "type": "text",
                        "widget": "list_preview", "fullWidth": True,
                        "widgetParams": {
                            "columns": [
                                {"key": "entity", "label": "Type", "width": 220},
                                {"key": "to_create", "label": "À créer", "width": 90},
                                {"key": "to_update", "label": "À mettre à jour", "width": 130},
                                {"key": "skipped", "label": "Laissés de côté", "width": 130},
                            ],
                            "listConfig": {"editableInline": False, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
                        },
                    },
                    {"key": "skipped_html", "type": "html", "label": " "},
                ],
                "submitLabel": "Importer",
                "rpc": "rpc_import",
                "rpcParams": {"students_file": "students_file", "parents_file": "parents_file", **_SELECTION_PARAMS},
            },
            {
                "id": "result",
                "title": "3. Résultat",
                "isLast": True,
                "fields": [{"key": "result_html", "type": "html", "label": " "}],
                "submitLabel": "Fermer",
            },
        ],
    }]

    def __init__(self, id, info_html=None, students_file=None, parents_file=None,
                 import_students=True, import_groups=False, import_options=True, import_responsables=True,
                 header_html=None, summary_rows=None, skipped_html=None, result_html=None):
        self.id = id
        self.info_html = info_html
        self.students_file = students_file
        self.parents_file = parents_file
        self.import_students = import_students
        self.import_groups = import_groups
        self.import_options = import_options
        self.import_responsables = import_responsables
        self.header_html = header_html
        self.summary_rows = summary_rows or []
        self.skipped_html = skipped_html
        self.result_html = result_html

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        return [cls(id=1, info_html=EXPERIMENTAL_NOTICE)]

    @staticmethod
    def _selection(**kwargs) -> dict:
        return {
            "students": bool(kwargs.get("import_students", False)),
            "groups": bool(kwargs.get("import_groups", False)),
            "options": bool(kwargs.get("import_options", False)),
            "persons": bool(kwargs.get("import_responsables", False)),
            "links": bool(kwargs.get("import_responsables", False)),
        }

    @requires_access("write")
    def rpc_analyze(self, db: Session, students_file=None, parents_file=None, **kwargs) -> dict:
        """Lit les fichiers, contrôle année et RNE. N'écrit rien."""
        students_flux, parents_flux, school = _load(db, students_file, parents_file)
        selection = self._selection(**kwargs)
        plan = _build_plan(db, students_flux, parents_flux, school, selection)
        return {
            "header_html": _header_html(students_flux, parents_flux, school),
            "summary_rows": _summary_rows(plan),
            "skipped_html": _skipped_html(plan),
        }

    @requires_access("write")
    def rpc_import(self, db: Session, students_file=None, parents_file=None, **kwargs) -> dict:
        """
        Rejoue l'analyse (le fichier n'a pas changé, mais la base a pu bouger entre les deux
        écrans) puis écrit. Ordre imposé : élèves d'abord (pour construire la correspondance
        ELEVE_ID -> Student), groupes et options ensuite (dépendent des élèves), responsables et
        rattachements en dernier (dépendent des deux).
        """
        students_flux, parents_flux, school = _load(db, students_file, parents_file)
        selection = self._selection(**kwargs)
        plan = _build_plan(db, students_flux, parents_flux, school, selection)

        students_par_eleve_id, students_compteurs, mefs_rattaches = _apply_students(db, students_flux, school, selection, plan)
        groups_compteurs = _apply_groups(db, students_flux, students_par_eleve_id, selection, plan)
        options_compteurs = _apply_options(db, students_flux, students_par_eleve_id, selection, plan)
        parents_par_personne_id, persons_compteurs = _apply_persons(db, parents_flux, selection, plan)
        links_compteurs = _apply_links(db, parents_flux, students_par_eleve_id, parents_par_personne_id, selection, plan)

        lignes = [
            f"<li><strong>Élèves</strong> : {students_compteurs['created']} créé(s), {students_compteurs['updated']} mis à jour</li>",
            f"<li><strong>Répartition dans les groupes</strong> : {groups_compteurs['created']} groupe(s) créé(s), {groups_compteurs['updated']} groupe(s) mis à jour</li>",
            f"<li><strong>Vœux de spécialité et options</strong> : {options_compteurs['created']} créé(s)</li>",
            f"<li><strong>Responsables</strong> : {persons_compteurs['created']} créé(s), {persons_compteurs['updated']} mis à jour</li>",
            f"<li><strong>Rattachements élèves ↔ responsables</strong> : {links_compteurs['created']} créé(s), {links_compteurs['updated']} mis à jour</li>",
        ]
        if mefs_rattaches:
            lignes.append(
                f"<li><strong>MEF rattachés dynamiquement à une division</strong> (le MEF existait déjà "
                f"en base mais n'était pas encore lié à la division de l'élève) : {mefs_rattaches}</li>"
            )
        html = f"<p>Import terminé pour « {esc(school.name)} ».</p><ul>{''.join(lignes)}</ul>"
        html += _skipped_html(plan)
        return {
            "result_html": html,
            "mutated_resources": [
                "students", "student_specialty_choices", "student_parent_links", "parents",
                "divisions", "mef_divisions", "groups", "partitions", "class_parts",
                "ref_exit_reasons", "ref_jobs", "ref_relative_links", "ref_external_schools",
                "ref_cities", "ref_countries",
            ],
        }

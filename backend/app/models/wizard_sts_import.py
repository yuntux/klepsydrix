"""
Wizard « Importer un flux STS-web » — quatre étapes (fichier / correspondances / aperçu /
résultat), même patron que wizard_specialty_group_generation.py (TransientModel + __actions__).

Sens traité : **descendant uniquement**, `sts_emp_<RNE>_<ANNEE>.xml`, celui que STS-web produit
par Exports puis Emploi du temps. La lecture du XML est déléguée à backend/app/core/sts_flux.py,
qui ne touche pas la base ; ce module ne fait que résoudre les correspondances et écrire.

**Deux garde-fous avant toute écriture**, tous deux bloquants :
- l'année du fichier doit être celle de la base (SystemSettingKey.SCHOOL_YEAR) — une base
  Klepsydrix vaut pour une année et une seule ;
- le RNE du fichier doit être celui d'un établissement de la base, et c'est cet établissement
  qui reçoit tous les objets créés. Un fichier par RNE : une cité scolaire s'importe en autant
  de passes qu'elle compte d'établissements.

**Politique d'écriture** : créer ce qui manque, mettre à jour ce qui existe déjà, ne jamais
supprimer. **Les codes du flux STS sont des clés** : l'appariement se fait dessus —
`code_nomenclature` pour une matière, `code_national` pour un MEF, `epp_id` pour un enseignant,
`code` pour une classe, `name` pour un groupe. C'est ce qui rend une table d'appariement inutile
à ce stade : les codes suffisent tant que la base est alimentée par le flux lui-même.

Un code reçu du flux est donc repris **tel quel**, jamais réécrit ni suffixé — sans quoi il
cesserait d'être une clé et le prochain import ne retrouverait plus l'enregistrement. Si le code
est déjà porté par un AUTRE enregistrement de la base, c'est un conflit de données : il est
signalé dans le rapport et l'objet est laissé de côté, à l'utilisateur de trancher.

**Deux informations manquent au flux alors que le modèle les exige** : la discipline d'une
matière et le niveau d'un MEF. Elles sont pré-remplies par déduction quand c'est possible, puis
**soumises à l'utilisateur** à la deuxième étape — jamais devinées en silence. La déduction de la
discipline passe par les services du flux, or « une part significative des établissements ne
saisit pas ses services dans STS-web » : elle échoue donc souvent, et c'est bien l'utilisateur
qui tranche.

**Import des services** : possible, mais décoché par défaut. Un `Service` Klepsydrix descend
obligatoirement d'un `MefService`, que le flux ne contient pas — ni volume horaire par MEF, ni
répartition classe entière / effectif réduit / dédoublé. L'import crée donc le `MefService`
manquant **à volumes nuls**, laisse sa cascade native engendrer les `Service` (voir
Service.generate_from_mef_service), et n'y ajoute que les enseignants du flux. Les volumes
restent à saisir en pré-rentrée. EDT fait le même choix de défaut : « dans la plupart des cas,
vous importez uniquement les MEF, les enseignants et les classes ».
"""
import base64
import unicodedata

from sqlalchemy.orm import Session

from backend.app.core.sts_flux import parse, StsFluxError
from backend.app.models.base import TransientModel, requires_access
from backend.app.models.discipline import Discipline
from backend.app.models.gender import GENDER_FROM_STS
from backend.app.models.division import Division
from backend.app.models.group import ClassPart, Group, Partition, _partition_code
from backend.app.models.mef import Mef, MefDivision, MefService
from backend.app.models.ref_academie import RefAcademie
from backend.app.models.ref_city import RefCity
from backend.app.models.ref_function import RefFunction
from backend.app.models.ref_election_method import RefElectionMethod
from backend.app.models.ref_grade import RefGrade
from backend.app.models.ref_level import RefLevel
from backend.app.models.school import School
from backend.app.models.service import Service
from backend.app.models.subject import Subject
from backend.app.models.system_setting import SystemSetting
from backend.app.models.teacher import Teacher, TeacherDiscipline

# Types d'objets proposés à l'import, dans l'ordre où ils doivent être traités : chacun peut
# dépendre des précédents (une matière a besoin d'une discipline, un MEF d'un établissement,
# une classe d'un MEF, un service de tout ce qui précède).
ENTITY_LABELS = [
    ("school", "Données communes de l'établissement"),
    ("disciplines", "Disciplines"),
    ("subjects", "Matières"),
    ("mefs", "MEF"),
    ("teachers", "Enseignants"),
    ("divisions", "Classes"),
    ("groups", "Groupes"),
    ("services", "Services"),
]

# Au-delà, la liste des absents est tronquée : elle est informative, elle ne doit pas noyer le
# reste de l'écran quand on importe un flux partiel dans une base déjà bien remplie.
MISSING_DISPLAY_LIMIT = 20

EXPERIMENTAL_NOTICE = (
    '<div style="border-left:4px solid #3B82F6;background:#EFF6FF;padding:12px 16px;'
    'border-radius:4px;margin-bottom:16px;">'
    "<p><strong>Fonction expérimentale.</strong> Le ministère ne publie pas sur son site public "
    "les normes d'échange STS, et l'auteur ne dispose d'aucun fichier d'exemple réel. La "
    "structure des fichiers a été déduite du code de deux logiciels libres, "
    "<strong>GEPI</strong> et <strong>CDT</strong> ; elle est probablement incomplète.</p>"
    "<p>Si vous disposez des spécifications officielles, ou d'exemples de fichiers "
    "pseudonymisés, n'hésitez pas à me les envoyer.</p>"
    "</div>"
)


def _normalize(value: str) -> str:
    """Majuscules sans accent ni espace superflu, pour les rapprochements de libellés."""
    if not value:
        return ""
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sans_accent.upper().split())


def _decode_upload(sts_file) -> bytes:
    """
    Extrait les octets d'un champ `type: "binary"` — un objet {filename, mime_type, data_base64},
    voir architecture.md §15.Q.
    """
    if not sts_file:
        raise ValueError("Aucun fichier n'a été fourni.")
    if isinstance(sts_file, (bytes, bytearray)):
        return bytes(sts_file)
    if isinstance(sts_file, str):
        return base64.b64decode(sts_file)
    data = (sts_file or {}).get("data_base64")
    if not data:
        raise ValueError("Le fichier fourni est vide ou illisible.")
    return base64.b64decode(data)


def _load(db: Session, sts_file):
    """Parse + contrôles bloquants, factorisé entre les trois RPC."""
    try:
        flux = parse(_decode_upload(sts_file))
    except StsFluxError as exc:
        raise ValueError(str(exc)) from exc
    return flux, _resolve_school(db, flux)


def _resolve_school(db: Session, flux) -> School:
    """
    Contrôles bloquants d'année et de RNE. Ils précèdent toute écriture : importer un fichier
    d'une autre année ou d'un autre établissement mélangerait deux structures pédagogiques sans
    qu'aucune contrainte du modèle ne s'en aperçoive.
    """
    expected_year = SystemSetting.get_school_year(db)
    if flux.school_year != expected_year:
        raise ValueError(
            f"Ce fichier porte l'année scolaire {flux.school_year}-{flux.school_year + 1} alors "
            f"que cette base est celle de {expected_year}-{expected_year + 1}. Une base vaut pour "
            f"une année et une seule : importez le flux de la bonne année, ou corrigez le "
            f"paramètre système « Année scolaire »."
        )

    school = db.query(School).filter(School.uai == flux.uai).first()
    if not school:
        connus = ", ".join(s.uai for s in db.query(School).order_by(School.uai).all()) or "aucun"
        raise ValueError(
            f"Le RNE {flux.uai} de ce fichier ne correspond à aucun établissement de la base "
            f"(RNE connus : {connus}). Créez l'établissement au préalable, ou importez le flux du "
            f"bon RNE — STS-web produit un fichier par établissement."
        )
    return school


# --------------------------------------------------------------------------------------------
#  Déductions : pré-remplissage des deux informations que le flux ne porte pas
# --------------------------------------------------------------------------------------------

def _guess_subject_disciplines(flux) -> dict:
    """
    Discipline de rattachement de chaque matière, INFÉRÉE et non lue : le flux ne porte pas ce
    lien. On remonte la chaîne matière -> services qui la référencent -> enseignants de ces
    services -> disciplines de ces enseignants ; retenue seulement si elle est unique.

    Cette déduction échoue souvent — une part significative des établissements ne saisit pas ses
    services dans STS-web, et sans service la chaîne est vide. C'est un simple pré-remplissage,
    l'utilisateur tranche à l'étape « Correspondances ».
    """
    disciplines_par_prof = {t["epp_id"]: set(t["discipline_codes"]) for t in flux.teachers}
    codes = {}
    for structure in list(flux.divisions) + list(flux.groups):
        for service in structure["services"]:
            trouvees = codes.setdefault(service["code_nomenclature"], set())
            for epp_id in service["teacher_epp_ids"]:
                trouvees |= disciplines_par_prof.get(epp_id, set())
    return {code: next(iter(v)) for code, v in codes.items() if len(v) == 1}


def _match_ref_grade(db: Session, mef_label: str):
    """
    Niveau de formation d'un MEF, déduit de son libellé : « 6EME SECTION SPORTIVE » porte le
    niveau « 6EME ». Le flux ne contient pas le niveau, et Mef.ref_grade_id est obligatoire.
    Rapprochement par inclusion du libellé de RefGrade, le plus long d'abord pour que
    « TERMINALE » l'emporte sur un éventuel préfixe plus court. Simple pré-remplissage.
    """
    label = _normalize(mef_label)
    grades = sorted(db.query(RefGrade).all(), key=lambda g: len(g.name or ""), reverse=True)
    for grade in grades:
        if _normalize(grade.name) and _normalize(grade.name) in label:
            return grade
    return None


def _resolution_rows(db: Session, flux) -> tuple:
    """
    Lignes de l'étape « Correspondances » : un MEF à rattacher à un niveau, une matière à
    rattacher à une discipline. Seuls les objets **à créer** y figurent — ceux déjà en base ont
    déjà leur rattachement, l'import ne le remet pas en cause.
    """
    devinees = _guess_subject_disciplines(flux)
    disciplines_du_flux = {c for t in flux.teachers for c in t["discipline_codes"]}

    mef_rows = []
    for mef in flux.mefs:
        if db.query(Mef).filter(Mef.code_national == mef["code_national"]).first():
            continue
        grade = _match_ref_grade(db, mef["name"])
        mef_rows.append({
            "id": mef["code_national"],
            "code": mef["code_national"],
            "label": mef["name"],
            "ref_grade_id": grade.id if grade else None,
        })

    subject_rows = []
    for subject in flux.subjects:
        code = subject["code_nomenclature"]
        if db.query(Subject).filter(Subject.code_nomenclature == code).first():
            continue
        # Repli : dans les flux où les deux nomenclatures coïncident, la discipline porte le même
        # code que la matière.
        code_discipline = devinees.get(code) or (code if code in disciplines_du_flux else None)
        discipline = (
            db.query(Discipline).filter(Discipline.code == code_discipline).first()
            if code_discipline else None
        )
        subject_rows.append({
            "id": code,
            "code": code,
            "label": subject["name"] or code,
            # Non résolue si la discipline n'existe pas encore en base : elle sera créée par
            # l'import, mais son id n'existe pas au moment où l'utilisateur choisit. On laisse
            # donc le code, exploité au moment de l'écriture.
            "discipline_id": discipline.id if discipline else None,
            "guessed_discipline_code": code_discipline,
        })

    return mef_rows, subject_rows


def _resolutions(mef_rows, subject_rows) -> dict:
    """Normalise ce que l'étape « Correspondances » renvoie, éventuellement édité par l'utilisateur."""
    return {
        "mefs": {r["code"]: r.get("ref_grade_id") for r in (mef_rows or [])},
        "subjects": {
            r["code"]: (r.get("discipline_id"), r.get("guessed_discipline_code"))
            for r in (subject_rows or [])
        },
    }


# --------------------------------------------------------------------------------------------
#  Plan : ce qui sera créé, mis à jour, laissé de côté — et ce qui manque au fichier
# --------------------------------------------------------------------------------------------

def _build_missing(db: Session, flux, school: School) -> dict:
    """
    Objets **déjà en base et absents du fichier**. Purement informatif : l'import ne supprime
    jamais rien, mais l'écart mérite d'être vu — c'est lui qui révèle un enseignant parti, une
    classe fermée, ou tout simplement qu'on est en train d'importer le flux du mauvais RNE.

    Les modèles rattachés à un établissement sont filtrés dessus : le fichier ne concerne qu'un
    RNE, tout signaler d'un autre établissement de la base n'aurait aucun sens. Les matières,
    disciplines et groupes n'ont pas de rattachement, ils sont comparés en entier.

    Les enseignants **sans identifiant EPP sont signalés eux aussi** : ils ne peuvent pas figurer
    dans le fichier faute de clé d'appariement, et c'est précisément ce qu'il faut voir — un
    enseignant saisi à la main que le flux ne connaît pas ne remontera jamais vers STS-web.
    """
    codes_flux = {
        "disciplines": {c for t in flux.teachers for c in t["discipline_codes"]},
        "subjects": {s["code_nomenclature"] for s in flux.subjects},
        "mefs": {m["code_national"] for m in flux.mefs},
        "teachers": {t["epp_id"] for t in flux.teachers},
        "divisions": {d["code"] for d in flux.divisions},
        "groups": {g["code"] for g in flux.groups},
    }

    def absent(key, rows, code_attr, label_attr):
        return [
            {
                "code": getattr(r, code_attr) or "sans identifiant",
                "label": getattr(r, label_attr) or getattr(r, code_attr) or "?",
            }
            for r in rows
            if getattr(r, code_attr) not in codes_flux[key]
        ]

    return {
        "disciplines": absent("disciplines", db.query(Discipline).all(), "code", "name"),
        "subjects": absent("subjects", db.query(Subject).all(), "code_nomenclature", "name"),
        "mefs": absent("mefs", db.query(Mef).filter(Mef.school_id == school.id).all(), "code_national", "name"),
        "teachers": absent(
            "teachers",
            db.query(Teacher).filter(Teacher.school_id == school.id).all(),
            "epp_id", "last_name",
        ),
        "divisions": absent("divisions", db.query(Division).filter(Division.school_id == school.id).all(), "code", "name"),
        "groups": absent("groups", db.query(Group).all(), "name", "name"),
        # Ni l'établissement ni les services n'ont d'écart à mesurer : l'un est apparié par son
        # RNE, l'autre n'a pas de code national.
        "school": [],
        "services": [],
    }


def _flux_services(flux) -> list:
    """
    Services du flux, à plat, avec la structure qui les porte. Un service de groupe n'est pas
    importable pour l'instant (voir _apply_plan) mais figure ici pour être compté et signalé.
    """
    out = []
    for division in flux.divisions:
        for service in division["services"]:
            out.append({"kind": "division", "structure": division, "service": service})
    for groupe in flux.groups:
        for service in groupe["services"]:
            out.append({"kind": "group", "structure": groupe, "service": service})
    return out


def _build_plan(db: Session, flux, school: School, resolutions: dict) -> dict:
    """
    Ce qui serait créé, mis à jour ou laissé de côté — sans rien écrire. Utilisé par l'aperçu ET
    par l'import, pour que les deux ne puissent pas diverger.
    """
    plan = {key: {"create": [], "update": [], "skipped": []} for key, _ in ENTITY_LABELS}

    # L'établissement existe forcément : son RNE vient d'être apparié (voir _resolve_school).
    # L'import ne crée jamais d'établissement, il complète celui de la base.
    plan["school"]["update"].append({"code": flux.uai, "label": school.name})

    codes_disciplines = {c for t in flux.teachers for c in t["discipline_codes"]}
    for code in sorted(codes_disciplines):
        cible = "update" if db.query(Discipline).filter(Discipline.code == code).first() else "create"
        plan["disciplines"][cible].append({"code": code, "label": code})

    for subject in flux.subjects:
        code = subject["code_nomenclature"]
        libelle = subject["name"] or code
        if db.query(Subject).filter(Subject.code_nomenclature == code).first():
            plan["subjects"]["update"].append({"code": code, "label": libelle})
            continue
        discipline_id, code_devine = resolutions["subjects"].get(code, (None, None))
        if not discipline_id and not code_devine:
            plan["subjects"]["skipped"].append({
                "code": code, "label": libelle,
                "reason": "aucune discipline choisie à l'étape « Correspondances »",
            })
            continue
        # Le code de gestion du flux est repris tel quel, jamais réécrit : c'est une clé. S'il
        # désigne déjà une AUTRE matière de la base, il y a conflit de données, pas doublon à
        # contourner — on le signale plutôt que d'inventer un code de repli.
        code_gestion = (subject["code_gestion"] or code)[:15]
        occupant = db.query(Subject).filter(Subject.code == code_gestion).first()
        if occupant:
            plan["subjects"]["skipped"].append({
                "code": code, "label": libelle,
                "reason": f"le code « {code_gestion} » désigne déjà la matière "
                          f"« {occupant.name} » ({occupant.code_nomenclature}) dans la base",
            })
            continue
        plan["subjects"]["create"].append({"code": code, "label": libelle})

    for mef in flux.mefs:
        code = mef["code_national"]
        if db.query(Mef).filter(Mef.code_national == code).first():
            plan["mefs"]["update"].append({"code": code, "label": mef["name"]})
        elif not resolutions["mefs"].get(code):
            plan["mefs"]["skipped"].append({
                "code": code, "label": mef["name"],
                "reason": "aucun niveau choisi à l'étape « Correspondances »",
            })
        else:
            plan["mefs"]["create"].append({"code": code, "label": mef["name"]})

    for teacher in flux.teachers:
        libelle = " ".join(filter(None, [teacher["last_name"], teacher["first_name"]])) or teacher["epp_id"]
        if not teacher["last_name"]:
            plan["teachers"]["skipped"].append({
                "code": teacher["epp_id"], "label": libelle, "reason": "aucun nom de famille",
            })
            continue
        if db.query(Teacher).filter(Teacher.epp_id == teacher["epp_id"]).first():
            plan["teachers"]["update"].append({"code": teacher["epp_id"], "label": libelle})
            continue
        # L'identifiant EPP devient le code de l'enseignant, tel quel. S'il est déjà porté par un
        # autre enseignant, c'est un conflit de données à trancher à la main.
        occupant = db.query(Teacher).filter(Teacher.code == teacher["epp_id"][:30]).first()
        if occupant:
            plan["teachers"]["skipped"].append({
                "code": teacher["epp_id"], "label": libelle,
                "reason": f"le code « {teacher['epp_id'][:30]} » désigne déjà l'enseignant "
                          f"« {occupant.last_name} » dans la base",
            })
            continue
        plan["teachers"]["create"].append({"code": teacher["epp_id"], "label": libelle})

    for division in flux.divisions:
        cible = "update" if db.query(Division).filter(Division.code == division["code"]).first() else "create"
        plan["divisions"][cible].append({"code": division["code"], "label": division["name"]})

    from backend.app.core.sts_naming import validate_sts_group_name

    for groupe in flux.groups:
        if db.query(Group).filter(Group.name == groupe["code"]).first():
            plan["groups"]["update"].append({"code": groupe["code"], "label": groupe["name"]})
            continue
        try:
            validate_sts_group_name(groupe["code"])
        except ValueError as exc:
            plan["groups"]["skipped"].append({
                "code": groupe["code"], "label": groupe["name"], "reason": str(exc),
            })
            continue
        plan["groups"]["create"].append({"code": groupe["code"], "label": groupe["name"]})

    for entree in _flux_services(flux):
        structure, service = entree["structure"], entree["service"]
        libelle = f"{structure['code']} / {service['code_nomenclature']}"
        if entree["kind"] == "group":
            plan["services"]["skipped"].append({
                "code": libelle, "label": libelle,
                "reason": "service porté par un groupe — non importé pour l'instant, le MEF de "
                          "rattachement n'est pas déterminable quand le groupe couvre plusieurs classes",
            })
            continue
        if not structure["mef_codes"]:
            plan["services"]["skipped"].append({
                "code": libelle, "label": libelle,
                "reason": "la classe n'est rattachée à aucun MEF dans le fichier",
            })
            continue
        plan["services"]["create"].append({"code": libelle, "label": libelle})

    return plan


# --------------------------------------------------------------------------------------------
#  Écriture
# --------------------------------------------------------------------------------------------

def _parse_date(valeur: str):
    """Date ISO du flux STS (AAAA-MM-JJ, voir FORMATS_JUSTIFICATION.md §2.3). None si illisible :
    une date mal formée ne doit pas faire échouer tout l'import."""
    from datetime import date as _date
    if not valeur:
        return None
    try:
        annee, mois, jour = str(valeur).strip()[:10].split("-")
        return _date(int(annee), int(mois), int(jour))
    except (ValueError, TypeError):
        return None


def _find_or_create_ref(db: Session, model, code: str, name: str = None):
    """
    Appariement d'un référentiel sur son `code`, avec création de la ligne si le code est inconnu.

    Employé pour les nomenclatures que le flux désigne par un code sans que Klepsydrix en
    connaisse la liste exhaustive : grade, fonction, académie. Perdre l'information parce qu'un
    code n'est pas seedé serait pire que d'ajouter une ligne au référentiel — et l'utilisateur
    peut toujours en corriger le libellé après coup.
    """
    code = (code or "").strip()
    if not code:
        return None
    existant = db.query(model).filter(model.code == code).first()
    if existant:
        return existant.id
    return model.create(db, {"code": code[:20], "name": (name or code)[:100]}).id


def _apply_school(db: Session, flux, school: School) -> int:
    """
    Données communes de l'établissement (PARAMETRES/UAJ et ANNEE_SCOLAIRE).

    Deux référentiels sont alimentés à la demande plutôt que seedés : l'académie
    (RefAcademie, appariée sur son code) et la commune (RefCity, appariée sur le couple
    nom + code postal, qui est la clé d'unicité du modèle).

    Seules les valeurs réellement présentes dans le fichier sont écrites : une balise absente
    laisse le champ de la base intact, elle ne l'efface pas.
    """
    infos = flux.school or {}
    vals = {
        "name": (infos.get("denom_princ") or school.name)[:100],
        "long_name": (infos.get("denom_compl") or None) and infos["denom_compl"][:200],
        "sigle": (infos.get("sigle") or None) and infos["sigle"][:20],
        "code_nature": (infos.get("code_nature") or None) and infos["code_nature"][:10],
        "code_categorie": (infos.get("code_categorie") or None) and infos["code_categorie"][:10],
        "statut": (infos.get("statut") or None) and infos["statut"][:50],
        "etablissement_sensible": (infos.get("etablissement_sensible") or None) and infos["etablissement_sensible"][:10],
        "address": (infos.get("address") or None) and infos["address"][:200],
        "zip_code": (infos.get("zip_code") or None) and infos["zip_code"][:20],
        "po_box": (infos.get("po_box") or None) and infos["po_box"][:50],
        "cedex": (infos.get("cedex") or None) and infos["cedex"][:50],
        "phone": (infos.get("phone") or None) and infos["phone"][:20],
        "student_start_date": _parse_date(infos.get("date_debut")),
        "student_end_date": _parse_date(infos.get("date_fin")),
        "academie_id": _find_or_create_ref(db, RefAcademie, infos.get("academie_code"), infos.get("academie_name")),
    }

    commune = (infos.get("commune") or "").strip()
    if commune:
        code_postal = (infos.get("zip_code") or None) and infos["zip_code"][:20]
        ville = db.query(RefCity).filter(RefCity.name == commune[:100], RefCity.zip_code == code_postal).first()
        if not ville:
            ville = RefCity.create(db, {"name": commune[:100], "zip_code": code_postal})
        vals["city_id"] = ville.id

    # Une balise absente n'efface rien : on n'écrit que ce que le fichier porte réellement.
    vals = {k: v for k, v in vals.items() if v is not None}
    school.update(db, vals)
    return 1


def _apply_plan(db: Session, flux, school: School, plan: dict, selection: dict, resolutions: dict) -> dict:
    """Exécute le plan pour les seuls types cochés. Ne supprime jamais rien."""
    compteurs = {key: {"created": 0, "updated": 0} for key, _ in ENTITY_LABELS}
    a_creer = {key: {e["code"] for e in plan[key]["create"]} for key, _ in ENTITY_LABELS}
    a_maj = {key: {e["code"] for e in plan[key]["update"]} for key, _ in ENTITY_LABELS}

    if selection.get("school"):
        compteurs["school"]["updated"] = _apply_school(db, flux, school)

    disciplines_par_code = {}
    if selection.get("disciplines"):
        # Libellés portés par INDIVIDU/DISCIPLINES/DISCIPLINE : le code n'est un repli que si le
        # flux ne donne aucun libellé.
        libelles = {
            d["code"]: d["name"]
            for t in flux.teachers for d in t["disciplines"] if d["name"]
        }
        for code in sorted(a_creer["disciplines"] | a_maj["disciplines"]):
            libelle = (libelles.get(code) or code)[:100]
            existant = db.query(Discipline).filter(Discipline.code == code).first()
            if existant:
                existant.update(db, {"name": libelle})
                disciplines_par_code[code] = existant
                compteurs["disciplines"]["updated"] += 1
            else:
                disciplines_par_code[code] = Discipline.create(db, {"code": code, "name": libelle})
                compteurs["disciplines"]["created"] += 1
    for discipline in db.query(Discipline).all():
        disciplines_par_code.setdefault(discipline.code, discipline)

    subjects_par_code = {}
    if selection.get("subjects"):
        for subject in flux.subjects:
            code = subject["code_nomenclature"]
            short_name = (subject["short_name"] or code)[:30]
            name = (subject["name"] or short_name)[:100]
            existant = db.query(Subject).filter(Subject.code_nomenclature == code).first()
            if existant and code in a_maj["subjects"]:
                existant.update(db, {"short_name": short_name, "name": name})
                subjects_par_code[code] = existant
                compteurs["subjects"]["updated"] += 1
            elif code in a_creer["subjects"]:
                discipline_id, code_devine = resolutions["subjects"].get(code, (None, None))
                discipline = (
                    db.get(Discipline, discipline_id) if discipline_id
                    else disciplines_par_code.get(code_devine)
                )
                if not discipline:
                    continue
                subjects_par_code[code] = Subject.create(db, {
                    "code": (subject["code_gestion"] or code)[:15],
                    "code_nomenclature": code,
                    "short_name": short_name,
                    "name": name,
                    "discipline_id": discipline.id,
                })
                compteurs["subjects"]["created"] += 1
    for subject in db.query(Subject).all():
        subjects_par_code.setdefault(subject.code_nomenclature, subject)

    mefs_par_code = {}
    if selection.get("mefs"):
        for mef in flux.mefs:
            code = mef["code_national"]
            existant = db.query(Mef).filter(Mef.code_national == code).first()
            if existant and code in a_maj["mefs"]:
                existant.update(db, {"name": mef["name"][:100]})
                mefs_par_code[code] = existant
                compteurs["mefs"]["updated"] += 1
            elif code in a_creer["mefs"]:
                mefs_par_code[code] = Mef.create(db, {
                    "school_id": school.id,
                    "code_national": code,
                    "name": mef["name"][:100],
                    "ref_grade_id": resolutions["mefs"][code],
                })
                compteurs["mefs"]["created"] += 1
    for mef in db.query(Mef).all():
        mefs_par_code.setdefault(mef.code_national, mef)

    teachers_par_epp = {}
    if selection.get("teachers"):
        for teacher in flux.teachers:
            epp_id = teacher["epp_id"]
            vals = {
                "last_name": (teacher["last_name"] or "")[:50],
                "first_name": (teacher["first_name"] or None) and teacher["first_name"][:50],
                "is_epp": teacher["is_epp"],
                "birth_last_name": (teacher["birth_last_name"] or None) and teacher["birth_last_name"][:50],
                "birth_date": _parse_date(teacher["birth_date"]),
                "gender": GENDER_FROM_STS.get((teacher["sexe"] or "").strip()),
                # GRADE et FONCTION sont appariés sur le CODE de leur référentiel ; la ligne est
                # créée si le code est inconnu, plutôt que de perdre l'information.
                "level_id": _find_or_create_ref(db, RefLevel, teacher["grade_code"]),
                "function_id": _find_or_create_ref(db, RefFunction, teacher["fonction_code"]),
            }
            vals = {k: v for k, v in vals.items() if v is not None or k in ("last_name", "is_epp")}
            existant = db.query(Teacher).filter(Teacher.epp_id == epp_id).first()
            if existant and epp_id in a_maj["teachers"]:
                existant.update(db, vals)
                teachers_par_epp[epp_id] = existant
                compteurs["teachers"]["updated"] += 1
            elif epp_id in a_creer["teachers"]:
                cree = Teacher.create(db, {
                    **vals,
                    "code": epp_id[:30],
                    "epp_id": epp_id,
                    "school_id": school.id,
                })
                teachers_par_epp[epp_id] = cree
                compteurs["teachers"]["created"] += 1
            else:
                continue
            # Lignes discipline (INDIVIDU/DISCIPLINE du flux) : ajoutées si absentes, jamais
            # retirées — un enseignant peut porter dans la base des disciplines que le flux ignore.
            cible = teachers_par_epp[epp_id]
            deja = {ligne.discipline_id for ligne in cible.discipline_lines}
            for code in teacher["discipline_codes"]:
                discipline = disciplines_par_code.get(code)
                if discipline and discipline.id not in deja:
                    TeacherDiscipline.create(db, {"teacher_id": cible.id, "discipline_id": discipline.id})
                    deja.add(discipline.id)
    for teacher in db.query(Teacher).filter(Teacher.epp_id.isnot(None)).all():
        teachers_par_epp.setdefault(teacher.epp_id, teacher)

    divisions_par_code = {}
    if selection.get("divisions"):
        for division in flux.divisions:
            code = division["code"]
            existant = db.query(Division).filter(Division.code == code).first()
            if existant and code in a_maj["divisions"]:
                existant.update(db, {"name": division["name"][:50]})
                divisions_par_code[code] = existant
                compteurs["divisions"]["updated"] += 1
            elif code in a_creer["divisions"]:
                divisions_par_code[code] = Division.create(db, {
                    "code": code, "name": division["name"][:50], "school_id": school.id,
                })
                compteurs["divisions"]["created"] += 1
            else:
                continue
            # Rattachement aux MEF, en création seulement : retirer un MefDivision existant
            # supprimerait en cascade les Service générés (voir service.py).
            cible = divisions_par_code[code]
            deja = {lien.mef_id for lien in cible.mef_links}
            for mef_code in division["mef_codes"]:
                mef = mefs_par_code.get(mef_code)
                if mef and mef.id not in deja:
                    MefDivision.create(db, {"mef_id": mef.id, "division_id": cible.id})
                    deja.add(mef.id)

        # Professeurs principaux, une fois classes et enseignants en place.
        for teacher in flux.teachers:
            cible = teachers_par_epp.get(teacher["epp_id"])
            if not cible:
                continue
            for code_structure in teacher["main_teacher_of"]:
                division = divisions_par_code.get(code_structure) or db.query(Division).filter(
                    Division.code == code_structure
                ).first()
                if division and division.main_teacher_id != cible.id:
                    division.update(db, {"main_teacher_id": cible.id})
    for division in db.query(Division).filter(Division.school_id == school.id).all():
        divisions_par_code.setdefault(division.code, division)

    if selection.get("groups"):
        for groupe in flux.groups:
            code = groupe["code"]
            libelle = (groupe["name"] or None) and groupe["name"][:100]
            if code in a_creer["groups"]:
                cible = Group.create(db, {"name": code, "long_name": libelle})
                compteurs["groups"]["created"] += 1
            elif code in a_maj["groups"]:
                # Le nom EST le code, il a servi à l'appariement : seul le libellé long se met
                # à jour.
                cible = db.query(Group).filter(Group.name == code).first()
                if cible and libelle:
                    cible.update(db, {"long_name": libelle})
                compteurs["groups"]["updated"] += 1
            else:
                continue
            _attach_group_divisions(db, cible, groupe, divisions_par_code)

    if selection.get("services"):
        compteurs["services"] = _apply_services(
            db, flux, plan, divisions_par_code, subjects_par_code, mefs_par_code, teachers_par_epp
        )

    return compteurs


def _attach_group_divisions(db: Session, group, groupe: dict, divisions_par_code: dict):
    """
    Rattache le groupe aux classes que le fichier lui donne
    (`DIVISIONS_APPARTENANCE/DIVISION_APPARTENANCE`).

    Un `Group` Klepsydrix ne connaît pas les divisions directement : il est composé de
    `ClassPart`, chacune appartenant à une `Partition` d'une division. Le flux ne décrit ni
    partition ni découpage — il dit seulement « ce groupe puise des élèves dans cette classe ».
    On matérialise donc, pour chaque classe rattachée, **une partition ne contenant que la partie
    de ce groupe** : c'est la traduction la plus fidèle d'une information qui ne dit rien de plus,
    et elle laisse au planificateur la liberté de réorganiser ensuite.

    La partition est identifiée par le code du groupe, donc stable : un ré-import retrouve la même
    et n'en crée pas une seconde. Aucun élève n'est réparti — le flux `sts_emp` n'en porte pas.
    """
    for code_division in groupe["division_codes"]:
        division = divisions_par_code.get(code_division) or db.query(Division).filter(
            Division.code == code_division
        ).first()
        if not division:
            continue

        code_partition = _partition_code(db, division.id, f"STS_{group.name}")
        partition = db.query(Partition).filter(Partition.code == code_partition).first()
        if not partition:
            partition = Partition.create(db, {
                "code": code_partition,
                "name": group.long_name or group.name,
                "division_id": division.id,
                "is_system_generated": True,
            })

        class_part = db.query(ClassPart).filter(
            ClassPart.partition_id == partition.id, ClassPart.name == group.name
        ).first()
        if not class_part:
            class_part = ClassPart.create(db, {
                "partition_id": partition.id,
                "name": group.name,
                "is_system_generated": True,
                "_system_write": True,
            })
        if class_part.id not in {cp.id for cp in group.class_parts}:
            group.update(db, {"class_part_ids": sorted({cp.id for cp in group.class_parts} | {class_part.id})})


def _programme_vals(db: Session, flux) -> dict:
    """
    Volumes horaires par couple (MEF, matière), issus de `NOMENCLATURES/PROGRAMMES`.

    Cette section est **PROUVÉE dans Nomenclature.xml** (fichier SIECLE, racine
    `BEE_NOMENCLATURES`) où `PROGRAMME` porte `CODE_MEF`, `CODE_MATIERE`,
    `CODE_MODALITE_ELECT` et `HORAIRE` — heures hebdomadaires décimales de 0.00 à 8.00, attesté
    par le référentiel ministériel `DONNEES_REF.xml`. Elle n'a **jamais été observée dans un
    sts_emp** : ni le schéma reconstitué ni les fichiers d'exemple ne la portent, et la seule
    trace côté STS est un bloc commenté du lecteur de GEPI.

    On la lit donc **si elle est là**, sans en dépendre : quand un programme existe pour le
    couple, son horaire alimente le gabarit MefService et sa modalité d'élection le complète ;
    sinon le gabarit est créé à volumes nuls comme auparavant.

    L'horaire va entièrement en `weekly_duration_full_class_minutes` : le programme donne un
    volume total, jamais sa répartition entre classe entière, effectif réduit et dédoublé — c'est
    au planificateur de la ventiler en pré-rentrée. Il est arrondi au pas horaire de la grille,
    faute de quoi la contrainte de multiple du modèle le refuserait.
    """
    from backend.app.core.time_utils import STANDARD_TIMESLOT_DURATION_MIN_MINUTES  # noqa: F401
    pas = int(SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION"))
    methodes = {m.code: m.id for m in db.query(RefElectionMethod).all()}

    vals = {}
    for programme in flux.programmes:
        cle = (programme["code_national"], programme["code_nomenclature"])
        entree = {}
        try:
            minutes = round(float(programme["horaire"] or 0) * 60 / pas) * pas
        except (TypeError, ValueError):
            minutes = 0
        if minutes:
            entree["weekly_duration_full_class_minutes"] = minutes
        methode = methodes.get((programme["election_code"] or "").strip())
        if methode:
            entree["election_method_id"] = methode
        if entree:
            vals[cle] = entree
    return vals


def _apply_services(db, flux, plan, divisions_par_code, subjects_par_code, mefs_par_code, teachers_par_epp) -> dict:
    """
    Import des services de classe entière.

    Le flux ne contient aucun `MefService`, et un `Service` n'existe pas sans lui. On crée donc
    le gabarit manquant **à volumes nuls**, et on laisse sa cascade native engendrer les
    `Service` (MefService.create() -> Service.generate_from_mef_service, un par MefDivision du
    MEF). L'import ne crée jamais un `Service` directement : il retrouve celui que la cascade
    vient de produire et n'y ajoute que les enseignants du flux.

    Conséquences à connaître, toutes deux annoncées dans le rapport :
    - les volumes horaires restent à saisir en pré-rentrée, le flux ne les porte pas ;
    - créer un gabarit engendre un `Service` pour **toutes** les classes du MEF, y compris celles
      dont le fichier ne mentionne pas cette matière — c'est la cascade du modèle, pas une
      décision de l'import.

    Quand une classe appartient à plusieurs MEF (6e ordinaire et 6e section sportive, par
    exemple), **chacun reçoit son propre gabarit** et le service est pourvu dans chacun : le flux
    n'indique aucun MEF principal, et privilégier le premier déclaré perdrait de l'information.
    """
    # `created` compte les gabarits MefService réellement créés, `updated` les Service pourvus en
    # enseignants — et surtout pas les lignes de service du fichier : la cascade en engendre
    # davantage (un par classe du MEF), le chiffre serait faux dans les deux sens.
    compteurs = {"created": 0, "updated": 0}
    a_creer = {e["code"] for e in plan["services"]["create"]}
    programmes = _programme_vals(db, flux)

    for entree in _flux_services(flux):
        if entree["kind"] != "division":
            continue
        structure, service = entree["structure"], entree["service"]
        libelle = f"{structure['code']} / {service['code_nomenclature']}"
        if libelle not in a_creer:
            continue

        division = divisions_par_code.get(structure["code"])
        subject = subjects_par_code.get(service["code_nomenclature"])
        if not (division and subject):
            continue

        # Une classe peut appartenir à plusieurs MEF (6e ordinaire + 6e section sportive, par
        # exemple) : chacun reçoit son propre gabarit, et le service est pourvu dans chacun. Le
        # flux n'indique pas de MEF principal, et il n'y a aucune raison d'en privilégier un.
        for mef_code in structure["mef_codes"]:
            mef = mefs_par_code.get(mef_code)
            if not mef:
                continue

            mef_division = db.query(MefDivision).filter(
                MefDivision.mef_id == mef.id, MefDivision.division_id == division.id
            ).first()
            if not mef_division:
                continue

            mef_service = db.query(MefService).filter(
                MefService.mef_id == mef.id, MefService.subject_id == subject.id
            ).first()
            if not mef_service:
                # discipline_id omis : auto-dérivé de Subject.discipline_id (voir MefService).
                # La création déclenche la cascade qui engendre les Service.
                vals = {"mef_id": mef.id, "subject_id": subject.id}
                vals.update(programmes.get((mef.code_national, subject.code_nomenclature), {}))
                mef_service = MefService.create(db, vals)
                compteurs["created"] += 1

            cible = db.query(Service).filter(
                Service.mef_service_id == mef_service.id,
                Service.mef_division_id == mef_division.id,
            ).first()
            if not cible:
                continue

            epp_ids = [e for e in service["teacher_epp_ids"] if e in teachers_par_epp]
            deja = {t.id for t in cible.teachers}
            nouveaux = {teachers_par_epp[e].id for e in epp_ids} - deja
            if nouveaux:
                cible.update(db, {"teacher_ids": sorted(deja | nouveaux)})
                compteurs["updated"] += 1

    return compteurs


# --------------------------------------------------------------------------------------------
#  Rendu
# --------------------------------------------------------------------------------------------

def _summary_rows(plan: dict, missing: dict) -> list:
    return [
        {
            "entity": libelle,
            "to_create": len(plan[key]["create"]),
            "to_update": len(plan[key]["update"]),
            "skipped": len(plan[key]["skipped"]),
            "missing": len(missing[key]),
        }
        for key, libelle in ENTITY_LABELS
    ]


def _skipped_html(plan: dict) -> str:
    """
    Objets non importés, avec leur raison. La liste est tronquée par type, mais **le nombre total
    est toujours annoncé** : un import où quinze services de groupe passent à la trappe ne doit
    pas en montrer vingt sans dire qu'il y en avait plus.
    """
    lignes = []
    for key, libelle in ENTITY_LABELS:
        elements = plan[key]["skipped"]
        if not elements:
            continue
        lignes.append(f"<li><strong>{libelle}</strong> — {len(elements)} objet(s) :<ul>")
        for e in elements[:MISSING_DISPLAY_LIMIT]:
            lignes.append(f"<li>« {e['label']} » ({e['code']}) : {e['reason']}</li>")
        reste = len(elements) - min(len(elements), MISSING_DISPLAY_LIMIT)
        if reste:
            lignes.append(f"<li>… et {reste} autre(s), pour la même raison ou une raison voisine</li>")
        lignes.append("</ul></li>")
    if not lignes:
        return "<p>Aucun objet laissé de côté.</p>"
    return (
        "<p><strong>Objets laissés de côté</strong> — ils ne seront ni créés ni modifiés :</p>"
        f"<ul>{''.join(lignes)}</ul>"
    )


def _missing_html(missing: dict) -> str:
    """
    Objets déjà en base qui ne figurent pas dans le fichier. Rien ne leur arrive — l'import ne
    supprime jamais — mais l'écart se voit, ce qui permet de repérer un départ, une fermeture de
    classe, ou un fichier qui n'est pas celui qu'on croyait.
    """
    blocs = []
    for key, libelle in ENTITY_LABELS:
        elements = missing[key]
        if not elements:
            continue
        visibles = elements[:MISSING_DISPLAY_LIMIT]
        items = ", ".join(f"« {e['label']} » ({e['code']})" for e in visibles)
        reste = len(elements) - len(visibles)
        if reste:
            items += f", et {reste} autre(s)"
        blocs.append(f"<li><strong>{libelle}</strong> ({len(elements)}) : {items}</li>")
    if not blocs:
        return "<p>Tout ce que contient la base figure aussi dans le fichier.</p>"
    return (
        "<p><strong>Déjà en base, absents du fichier</strong> — rien ne leur arrive, l'import ne "
        "supprime jamais ; à vérifier s'il s'agit de départs ou de fermetures :</p>"
        f"<ul>{''.join(blocs)}</ul>"
    )


def _resolution_html(mef_rows, subject_rows) -> str:
    manquants = sum(1 for r in mef_rows if not r.get("ref_grade_id"))
    manquants += sum(
        1 for r in subject_rows
        if not r.get("discipline_id") and not r.get("guessed_discipline_code")
    )
    if not mef_rows and not subject_rows:
        return "<p>Rien à compléter : tous les objets du fichier existent déjà dans la base.</p>"
    entete = (
        "<p>Le fichier STS ne porte ni le niveau d'un MEF, ni la discipline d'une matière, alors "
        "que Klepsydrix les exige. Ce qui a pu être déduit est pré-rempli ; complétez le reste.</p>"
    )
    if manquants:
        entete += (
            f"<p><strong>{manquants} ligne(s) restent à compléter.</strong> Celles qui seront "
            "laissées vides ne seront pas importées, et figureront dans le rapport.</p>"
        )
    return entete


class WizardStsImport(TransientModel):
    """Enregistrement singleton (id=1 fixe, pas de liste), voir ui.json."""

    __tablename__ = "wizard_sts_imports"
    _fields = [
        "id", "sts_file", "info_html", "header_html", "resolution_html", "mef_rows",
        "subject_rows", "summary_rows", "skipped_html", "missing_html",
        "import_disciplines", "import_subjects", "import_mefs", "import_teachers",
        "import_divisions", "import_groups", "import_services", "result_html",
    ]
    _field_info = {
        "sts_file": {"label": "Fichier STS-web", "type": "binary"},
        "info_html": {"type": "html", "label": " ", "readOnly": True},
        "header_html": {"type": "html", "label": " ", "readOnly": True},
        "resolution_html": {"type": "html", "label": " ", "readOnly": True},
        "mef_rows": {"label": "MEF à rattacher à un niveau", "type": "text", "widget": "list_preview"},
        "subject_rows": {"label": "Matières à rattacher à une discipline", "type": "text", "widget": "list_preview"},
        "summary_rows": {"label": "Contenu du fichier", "type": "text", "widget": "list_preview", "readOnly": True},
        "skipped_html": {"type": "html", "label": " ", "readOnly": True},
        "missing_html": {"type": "html", "label": " ", "readOnly": True},
        "import_school": {"label": "Données communes de l'établissement", "type": "boolean"},
        "import_disciplines": {"label": "Disciplines", "type": "boolean"},
        "import_subjects": {"label": "Matières", "type": "boolean"},
        "import_mefs": {"label": "MEF", "type": "boolean"},
        "import_teachers": {"label": "Enseignants", "type": "boolean"},
        "import_divisions": {"label": "Classes", "type": "boolean"},
        "import_groups": {"label": "Groupes", "type": "boolean"},
        "import_services": {"label": "Services", "type": "boolean"},
        "result_html": {"type": "html", "label": " ", "readOnly": True},
    }

    # Paramètres repassés d'une étape à l'autre : le TransientModel ne persiste rien, c'est
    # l'état du formulaire côté navigateur qui porte le fichier et les choix de l'utilisateur.
    _SELECTION_PARAMS = {
        "import_school": "import_school",
        "import_disciplines": "import_disciplines",
        "import_subjects": "import_subjects",
        "import_mefs": "import_mefs",
        "import_teachers": "import_teachers",
        "import_divisions": "import_divisions",
        "import_groups": "import_groups",
        "import_services": "import_services",
    }

    __actions__ = [{
        "id": "import_sts_flux",
        "label": "Importer un flux STS-web",
        "type": "wizard",
        "steps": [
            {
                "id": "upload",
                "title": "1. Fichier et contenu à importer",
                "fields": [
                    {"key": "info_html", "type": "html", "label": " "},
                    {"key": "sts_file", "label": "Fichier STS-web", "type": "binary"},
                    {"key": "import_school", "label": "Importer les données communes de l'établissement (nom, académie, adresse, coordonnées…)", "type": "boolean"},
                    {"key": "import_disciplines", "label": "Importer les disciplines", "type": "boolean"},
                    {"key": "import_subjects", "label": "Importer les matières", "type": "boolean"},
                    {"key": "import_mefs", "label": "Importer les MEF", "type": "boolean"},
                    {"key": "import_teachers", "label": "Importer les enseignants", "type": "boolean"},
                    {"key": "import_divisions", "label": "Importer les classes", "type": "boolean"},
                    {"key": "import_groups", "label": "Importer les groupes", "type": "boolean"},
                    {"key": "import_services", "label": "Importer les services (volumes horaires à compléter ensuite)", "type": "boolean"},
                ],
                "submitLabel": "Analyser",
                "rpc": "rpc_analyze",
                "rpcParams": {"sts_file": "sts_file"},
            },
            {
                "id": "resolve",
                "title": "2. Correspondances",
                "fields": [
                    {"key": "header_html", "type": "html", "label": " "},
                    {"key": "resolution_html", "type": "html", "label": " "},
                    {
                        "key": "mef_rows", "label": "MEF à rattacher à un niveau", "type": "text",
                        "widget": "list_preview", "fullWidth": True,
                        "widgetParams": {
                            "columns": [
                                {"key": "code", "label": "Code MEF", "width": 130},
                                {"key": "label", "label": "Libellé", "width": 280},
                                {"key": "ref_grade_id", "label": "Niveau", "resource": "ref_grades", "editable": True, "width": 180},
                            ],
                            "listConfig": {"editableInline": True, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
                        },
                    },
                    {
                        "key": "subject_rows", "label": "Matières à rattacher à une discipline", "type": "text",
                        "widget": "list_preview", "fullWidth": True,
                        "widgetParams": {
                            "columns": [
                                {"key": "code", "label": "Code matière", "width": 130},
                                {"key": "label", "label": "Libellé", "width": 280},
                                {"key": "discipline_id", "label": "Discipline", "resource": "disciplines", "editable": True, "width": 180},
                            ],
                            "listConfig": {"editableInline": True, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
                        },
                    },
                ],
                "submitLabel": "Prévisualiser",
                "rpc": "rpc_preview",
                "rpcParams": {
                    "sts_file": "sts_file", "mef_rows": "mef_rows", "subject_rows": "subject_rows",
                    **_SELECTION_PARAMS,
                },
            },
            {
                "id": "review",
                "title": "3. Aperçu",
                "fields": [
                    {
                        "key": "summary_rows", "label": "Contenu du fichier", "type": "text",
                        "widget": "list_preview", "fullWidth": True,
                        "widgetParams": {
                            "columns": [
                                {"key": "entity", "label": "Type", "width": 160},
                                {"key": "to_create", "label": "À créer", "width": 90},
                                {"key": "to_update", "label": "À mettre à jour", "width": 130},
                                {"key": "skipped", "label": "Laissés de côté", "width": 130},
                                {"key": "missing", "label": "Absents du fichier", "width": 140},
                            ],
                            "listConfig": {"editableInline": False, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
                        },
                    },
                    {"key": "skipped_html", "type": "html", "label": " "},
                    {"key": "missing_html", "type": "html", "label": " "},
                ],
                "submitLabel": "Importer",
                "rpc": "rpc_import",
                "rpcParams": {
                    "sts_file": "sts_file", "mef_rows": "mef_rows", "subject_rows": "subject_rows",
                    **_SELECTION_PARAMS,
                },
            },
            {
                "id": "result",
                "title": "4. Résultat",
                "isLast": True,
                "fields": [{"key": "result_html", "type": "html", "label": " "}],
                "submitLabel": "Fermer",
            },
        ],
    }]

    def __init__(self, id, sts_file=None, info_html=None, header_html=None, resolution_html=None,
                 mef_rows=None, subject_rows=None, summary_rows=None, skipped_html=None,
                 missing_html=None, import_school=True, import_disciplines=True, import_subjects=True,
                 import_mefs=True, import_teachers=True, import_divisions=True,
                 import_groups=True, import_services=False, result_html=None):
        self.id = id
        self.sts_file = sts_file
        self.info_html = info_html
        self.header_html = header_html
        self.resolution_html = resolution_html
        self.mef_rows = mef_rows or []
        self.subject_rows = subject_rows or []
        self.summary_rows = summary_rows or []
        self.skipped_html = skipped_html
        self.missing_html = missing_html
        self.import_school = import_school
        self.import_disciplines = import_disciplines
        self.import_subjects = import_subjects
        self.import_mefs = import_mefs
        self.import_teachers = import_teachers
        self.import_divisions = import_divisions
        self.import_groups = import_groups
        self.import_services = import_services
        self.result_html = result_html

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        html = EXPERIMENTAL_NOTICE + (
            "<p>Sélectionnez le fichier <code>sts_emp_&lt;RNE&gt;_&lt;ANNÉE&gt;.xml</code> obtenu "
            "depuis STS-web par <em>Exports</em> puis <em>Emploi du temps</em>, et cochez ce que "
            "vous souhaitez en reprendre.</p>"
            "<p>L'import <strong>crée ce qui manque et met à jour ce qui existe déjà</strong> ; "
            "il ne supprime jamais rien. L'année et le RNE du fichier doivent correspondre à ceux "
            "de cette base.</p>"
            "<p>Les <strong>services</strong> sont décochés par défaut : le fichier ne porte pas "
            "les volumes horaires, qui resteront à saisir en pré-rentrée.</p>"
        )
        # import_services=False : seul type décoché par défaut, voir ci-dessus.
        return [cls(id=1, info_html=html)]

    @staticmethod
    def _selection(**kwargs) -> dict:
        return {key: bool(kwargs.get(f"import_{key}", False)) for key, _ in ENTITY_LABELS}

    @requires_access("write")
    def rpc_analyze(self, db: Session, sts_file=None) -> dict:
        """Lit le fichier, contrôle année et RNE, prépare les correspondances. N'écrit rien."""
        flux, school = _load(db, sts_file)
        mef_rows, subject_rows = _resolution_rows(db, flux)
        header = (
            f"<p><strong>{flux.school_name or school.name}</strong> — RNE {flux.uai} — année "
            f"scolaire {flux.school_year}-{flux.school_year + 1}.</p>"
            f"<p>Les objets créés seront rattachés à l'établissement « {school.name} ».</p>"
        )
        return {
            "header_html": header,
            "resolution_html": _resolution_html(mef_rows, subject_rows),
            "mef_rows": mef_rows,
            "subject_rows": subject_rows,
        }

    @requires_access("write")
    def rpc_preview(self, db: Session, sts_file=None, mef_rows=None, subject_rows=None, **kwargs) -> dict:
        """Aperçu, correspondances comprises. N'écrit toujours rien."""
        flux, school = _load(db, sts_file)
        plan = _build_plan(db, flux, school, _resolutions(mef_rows, subject_rows))
        missing = _build_missing(db, flux, school)
        return {
            "summary_rows": _summary_rows(plan, missing),
            "skipped_html": _skipped_html(plan),
            "missing_html": _missing_html(missing),
        }

    @requires_access("write")
    def rpc_import(self, db: Session, sts_file=None, mef_rows=None, subject_rows=None, **kwargs) -> dict:
        flux, school = _load(db, sts_file)
        resolutions = _resolutions(mef_rows, subject_rows)
        plan = _build_plan(db, flux, school, resolutions)
        # Calculé AVANT l'écriture : après, les objets du flux existent tous en base et l'écart
        # avec le fichier ne voudrait plus rien dire.
        missing = _build_missing(db, flux, school)
        selection = self._selection(**kwargs)
        compteurs = _apply_plan(db, flux, school, plan, selection, resolutions)

        lignes = []
        for key, libelle in ENTITY_LABELS:
            if not selection[key]:
                continue
            if key == "services":
                # Libellé propre : ici « créé » compte des gabarits MefService et « mis à jour »
                # des Service pourvus en enseignants — pas la même chose que pour les autres types.
                lignes.append(
                    f"<li><strong>{libelle}</strong> : {compteurs[key]['created']} gabarit(s) MEF "
                    f"créé(s), {compteurs[key]['updated']} service(s) pourvu(s) en enseignants</li>"
                )
            else:
                lignes.append(
                    f"<li><strong>{libelle}</strong> : {compteurs[key]['created']} créé(s), "
                    f"{compteurs[key]['updated']} mis à jour</li>"
                )
        html = f"<p>Import terminé pour « {school.name} ».</p><ul>{''.join(lignes) or '<li>Aucun type sélectionné.</li>'}</ul>"
        if selection["services"]:
            html += (
                "<p><strong>Services</strong> : les gabarits MEF créés au passage portent des "
                "volumes horaires nuls — le fichier STS ne les contient pas. Complétez-les dans "
                "« Pré-rentrée &gt; Services MEF » avant toute génération de cours.</p>"
                "<p>Créer un gabarit engendre un service pour <em>toutes</em> les classes de son "
                "MEF, y compris celles dont le fichier ne mentionne pas cette matière : c'est la "
                "cascade du modèle, pas une décision de l'import.</p>"
            )
        html += _skipped_html(plan)
        html += _missing_html(missing)
        return {
            "result_html": html,
            "mutated_resources": [
                "disciplines", "subjects", "mefs", "mef_services", "mef_divisions", "teachers",
                "teacher_disciplines", "divisions", "groups", "services",
            ],
        }

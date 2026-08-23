"""
Lecture du flux STS-web descendant : `sts_emp_<RNE>_<ANNEE>.xml`.

Module **pur** : il transforme un document XML en dictionnaires et ne touche jamais la base.
Toute la logique d'appariement et d'écriture est dans wizard_sts_import.py. Cette séparation
rend le parseur testable sur les fichiers d'exemple sans monter une base, et surtout
remplaçable sans risque le jour où le format sera mieux connu.

Le format n'est pas publié par le Ministère. La reconstitution utilisée ici est celle du
dossier d'analyse de GEPI et CDT. On lit ici tolérant : tout élément inconnu est ignoré, et
seuls l'établissement et l'année sont exigés, parce que ce sont les deux seules informations
sans lesquelles on ne peut pas décider si le fichier concerne bien cette base.

Le sens montant (`emp_sts_<RNE>_<ANNEE>.xml`, racine `EDT_STS`) n'est PAS traité ici : trois de
ses quatre familles de données ont des balises inconnues.
"""
from dataclasses import dataclass, field
# `defusedxml`, pas `xml.etree` : le fichier analysé ici est fourni par l'utilisateur. La
# bibliothèque standard ne charge pas d'entité EXTERNE (pas de XXE en Python 3), mais elle développe
# les entités INTERNES déclarées dans le prologue — de quoi faire exploser la mémoire du serveur
# avec un fichier de quelques kilo-octets (« billion laughs »), que le plafond de taille des envois
# (core/upload_limits.py) ne peut pas voir passer puisqu'il mesure le fichier, pas son expansion.
# `defusedxml` refuse ces déclarations au lieu de les dérouler.
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError

from backend.app.core.xml_text import text as _text, first_label as _first_label

STS_ROOT_TAG = "STS_EDT"
# Racine du fichier montant. On la reconnaît uniquement pour produire un message utile : c'est
# l'erreur que GEPI signale explicitement à ses utilisateurs, donc elle est courante.
EDT_ROOT_TAG = "EDT_STS"


class StsFluxError(ValueError):
    """Fichier illisible ou qui n'est pas un flux STS. Message destiné à l'utilisateur final."""


@dataclass
class StsFlux:
    """Contenu exploitable d'un flux STS, sans aucune résolution d'identifiant."""

    uai: str = None
    school_year: int = None
    school_name: str = None
    # Tout PARAMETRES/UAJ, plus les dates d'ANNEE_SCOLAIRE : repris tel quel, à charge du wizard
    # d'en faire des colonnes de School (voir wizard_sts_import, import_school).
    school: dict = field(default_factory=dict)
    subjects: list = field(default_factory=list)
    mefs: list = field(default_factory=list)
    teachers: list = field(default_factory=list)
    divisions: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    # NOMENCLATURES/PROGRAMMES : couples (MEF, matière) avec leur horaire hebdomadaire. Lu de
    # façon défensive — la section est PROUVÉE dans Nomenclature.xml (SIECLE) mais jamais
    # observée dans un sts_emp. Si elle y figure, elle donne les volumes des MefService ; sinon
    # la liste reste vide et l'import retombe sur les gabarits à zéro.
    programmes: list = field(default_factory=list)

    def counts(self) -> dict:
        """Volumétrie par type, pour l'écran d'aperçu du wizard."""
        return {
            "subjects": len(self.subjects),
            "mefs": len(self.mefs),
            "teachers": len(self.teachers),
            "divisions": len(self.divisions),
            "groups": len(self.groups),
            "programmes": len(self.programmes),
        }


def parse(content: bytes) -> StsFlux:
    """
    Analyse un flux STS descendant. Lève StsFluxError si le document n'en est pas un.
    `content` : octets du fichier, tels que reçus de l'upload.
    """
    try:
        root = ET.fromstring(content)
    except (ParseError, DefusedXmlException) as exc:
        # DefusedXmlException : le document est syntaxiquement valide mais contient une déclaration
        # d'entité refusée (voir l'import de defusedxml en tête de module). Message unique, comme
        # pour un XML malformé — la distinction n'aiderait pas l'utilisateur, qui n'a de toute
        # façon rien d'autre à faire que fournir un vrai export STS-web.
        raise StsFluxError(f"Le fichier n'est pas un document XML valide : {exc}") from exc

    if root.tag.upper() == EDT_ROOT_TAG:
        raise StsFluxError(
            "Ce fichier est un export de logiciel d'emploi du temps (racine EDT_STS), pas un "
            "export STS-web. Le fichier attendu se nomme sts_emp_<RNE>_<ANNEE>.xml et s'obtient "
            "depuis STS-web par Exports puis Emploi du temps."
        )
    if root.tag.upper() != STS_ROOT_TAG:
        raise StsFluxError(
            f"Ce fichier n'est pas un export STS-web : sa racine est « {root.tag} » au lieu de "
            f"« {STS_ROOT_TAG} »."
        )

    flux = StsFlux()
    _parse_parametres(root, flux)
    _parse_nomenclatures(root, flux)
    _parse_individus(root, flux)
    _parse_structure(root, flux)

    if not flux.uai:
        raise StsFluxError(
            "Le fichier ne porte aucun code établissement (PARAMETRES/UAJ). Impossible de "
            "vérifier qu'il concerne bien cette base."
        )
    if not flux.school_year:
        raise StsFluxError(
            "Le fichier ne porte aucune année scolaire (PARAMETRES/ANNEE_SCOLAIRE). Impossible "
            "de vérifier qu'il concerne bien l'année de cette base."
        )
    return flux


def _parse_parametres(root, flux: StsFlux):
    # XPath descendant plutôt que chemin absolu : la hiérarchie au-dessus de UAJ n'est pas
    # établie avec certitude (voir FORMATS_JUSTIFICATION.md §9.3), autant ne pas en dépendre.
    for uaj in root.iter("UAJ"):
        flux.uai = (uaj.get("CODE") or "").strip() or None
        flux.school_name = _first_label(uaj, "DENOM_PRINC", "DENOM_COMPL")
        academie = uaj.find("ACADEMIE")
        flux.school = {
            "denom_princ": _text(uaj, "DENOM_PRINC"),
            "denom_compl": _text(uaj, "DENOM_COMPL"),
            "academie_code": _text(academie, "CODE") if academie is not None else None,
            "academie_name": _text(academie, "LIBELLE") if academie is not None else None,
            "sigle": _text(uaj, "SIGLE"),
            "code_nature": _text(uaj, "CODE_NATURE"),
            "code_categorie": _text(uaj, "CODE_CATEGORIE"),
            "statut": _text(uaj, "STATUT"),
            "etablissement_sensible": _text(uaj, "ETABLISSEMENT_SENSIBLE"),
            "address": _text(uaj, "ADRESSE"),
            "commune": _text(uaj, "COMMUNE"),
            "zip_code": _text(uaj, "CODE_POSTAL"),
            "po_box": _text(uaj, "BOITE_POSTALE"),
            "cedex": _text(uaj, "CEDEX"),
            "phone": _text(uaj, "TELEPHONE"),
        }
        break
    for annee in root.iter("ANNEE_SCOLAIRE"):
        raw = (annee.get("ANNEE") or "").strip()
        if raw.isdigit():
            flux.school_year = int(raw)
        flux.school["date_debut"] = _text(annee, "DATE_DEBUT")
        flux.school["date_fin"] = _text(annee, "DATE_FIN")
        break


def _parse_nomenclatures(root, flux: StsFlux):
    for matiere in root.iter("MATIERE"):
        code = (matiere.get("CODE") or "").strip()
        if not code:
            continue
        flux.subjects.append({
            "code_nomenclature": code,
            "code_gestion": _text(matiere, "CODE_GESTION"),
            "short_name": _first_label(matiere, "LIBELLE_COURT", "LIBELLE_EDITION", "LIBELLE_LONG"),
            "name": _first_label(matiere, "LIBELLE_LONG", "LIBELLE_EDITION", "LIBELLE_COURT"),
        })

    for mef in root.iter("MEF"):
        # MEF apparaît à deux endroits : en nomenclature, où il porte ses libellés, et dans
        # DIVISION/MEFS_APPARTENANCE, où il n'a qu'un CODE. Seul le premier nous intéresse ici,
        # d'où le filtre sur la présence d'au moins un libellé.
        code = (mef.get("CODE") or "").strip()
        label = _first_label(mef, "LIBELLE_COURT", "LIBELLE_EDITION", "LIBELLE_LONG")
        if not code or not label:
            continue
        flux.mefs.append({"code_national": code, "name": label})

    for programme in root.iter("PROGRAMME"):
        code_mef = _text(programme, "CODE_MEF")
        code_matiere = _text(programme, "CODE_MATIERE")
        if not (code_mef and code_matiere):
            continue
        flux.programmes.append({
            "code_national": code_mef,
            "code_nomenclature": code_matiere,
            "election_code": _text(programme, "CODE_MODALITE_ELECT"),
            # Heures hebdomadaires en décimal, 0.00 à 8.00 (HoraireType).
            "horaire": _text(programme, "HORAIRE"),
        })


def _parse_individus(root, flux: StsFlux):
    for individu in root.iter("INDIVIDU"):
        epp_id = (individu.get("ID") or "").strip()
        if not epp_id:
            continue
        flux.teachers.append({
            "epp_id": epp_id,
            # @TYPE vaut `epp` ou `local`. Absent, on suppose `epp` : c'est le cas de loin le
            # plus fréquent, et l'attribut n'est pas systématiquement présent.
            "is_epp": (individu.get("TYPE") or "epp").strip().lower() != "local",
            "last_name": _first_label(individu, "NOM_USAGE", "NOM_PATRONYMIQUE"),
            "birth_last_name": _text(individu, "NOM_PATRONYMIQUE"),
            "first_name": _text(individu, "PRENOM"),
            "birth_date": _text(individu, "DATE_NAISSANCE"),
            "civilite": _text(individu, "CIVILITE"),
            # SEXE vaut 1 ou 2, GRADE et FONCTION sont des codes de nomenclature : la traduction
            # en valeurs Klepsydrix appartient au wizard, pas au parseur.
            "sexe": _text(individu, "SEXE"),
            "grade_code": _text(individu, "GRADE"),
            "fonction_code": _text(individu, "FONCTION"),
            "disciplines": [
                {
                    "code": (d.get("CODE") or "").strip(),
                    "name": _first_label(d, "LIBELLE_LONG", "LIBELLE_COURT"),
                }
                for d in individu.iter("DISCIPLINE")
                if (d.get("CODE") or "").strip()
            ],
            "discipline_codes": [
                (d.get("CODE") or "").strip()
                for d in individu.iter("DISCIPLINE")
                if (d.get("CODE") or "").strip()
            ],
            "main_teacher_of": [
                _text(pp, "CODE_STRUCTURE")
                for pp in individu.iter("PROF_PRINC")
                if _text(pp, "CODE_STRUCTURE")
            ],
        })


def _services(node) -> list:
    out = []
    for service in node.iter("SERVICE"):
        code_matiere = (service.get("CODE_MATIERE") or "").strip()
        if not code_matiere:
            continue
        out.append({
            "code_nomenclature": code_matiere,
            "modality_code": (service.get("CODE_MOD_COURS") or "").strip() or None,
            "teacher_epp_ids": [
                (e.get("ID") or "").strip()
                for e in service.iter("ENSEIGNANT")
                if (e.get("ID") or "").strip()
            ],
        })
    return out


def _parse_structure(root, flux: StsFlux):
    for division in root.iter("DIVISION"):
        # DIVISION apparaît aussi, self-fermante, sous GROUPE/DIVISIONS_APPARTENANCE dans les
        # fichiers antérieurs à la correction du nom de cet élément : une division sans code est
        # ignorée, et celles rencontrées sous un groupe le sont par le filtre sur SERVICES.
        code = (division.get("CODE") or "").strip()
        if not code:
            continue
        flux.divisions.append({
            "code": code,
            "name": _first_label(division, "LIBELLE_LONG", "LIBELLE_EDITION", "LIBELLE_COURT") or code,
            "mef_codes": [
                (m.get("CODE") or "").strip()
                for m in division.iter("MEF")
                if (m.get("CODE") or "").strip()
            ],
            "services": _services(division),
        })

    for groupe in root.iter("GROUPE"):
        code = (groupe.get("CODE") or "").strip()
        if not code:
            continue
        division_codes = [
            (d.get("CODE") or "").strip()
            for d in groupe.iter("DIVISION_APPARTENANCE")
            if (d.get("CODE") or "").strip()
        ]
        flux.groups.append({
            "code": code,
            "name": _first_label(groupe, "LIBELLE_LONG", "LIBELLE_EDITION", "LIBELLE_COURT") or code,
            "division_codes": division_codes,
            # Le cardinal porte à lui seul la nature du groupe : une division = portion de
            # classe, deux ou plus = regroupement inter-classes. Aucune balise ne le déclare.
            "is_regroupement": len(division_codes) > 1,
            "services": _services(groupe),
        })

"""
Lecture des flux SIECLE descendants « élèves avec adresses » et « responsables avec adresses »,
déposés au format XML — voir xsd_et_norme/ElevesAvecAdresses.xsd et
ResponsablesAvecAdresses.xsd du dossier d'analyse (racines BEE_ELEVES et BEE_RESPONSABLES).

Module **pur**, même principe que sts_flux.py : transforme le XML en dictionnaires, ne touche
jamais la base. Toute la résolution d'identifiants et l'écriture sont dans
wizard_eleves_import.py. Chaque fichier est parsé indépendamment : ce sont deux exports SIECLE
distincts (`Exploitation > Exports standard`), pas deux sections d'un même document.
"""
from dataclasses import dataclass, field

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError

from backend.app.core.xml_text import text as _text, first_label as _first_label

ELEVES_ROOT_TAG = "BEE_ELEVES"
RESPONSABLES_ROOT_TAG = "BEE_RESPONSABLES"
# Racines voisines de la même famille SIECLE, reconnues uniquement pour produire un message utile
# si l'utilisateur se trompe de fichier (même principe que sts_flux.py face à EDT_STS).
_KNOWN_SIECLE_ROOTS = {
    "BEE_NOMENCLATURES": "un export de nomenclatures (Nomenclature.xml)",
    "BEE_COMMUN": "un export de données communes d'établissement (Communs.xml)",
    ELEVES_ROOT_TAG: "un export « Élèves avec adresses » (ElevesAvecAdresses.xml)",
    RESPONSABLES_ROOT_TAG: "un export « Responsables avec adresses » (ResponsablesAvecAdresses.xml)",
}


class ElevesFluxError(ValueError):
    """Fichier illisible ou qui n'est pas l'export SIECLE attendu. Message destiné à l'utilisateur."""


@dataclass
class ElevesFlux:
    """Contenu exploitable du fichier ÉlèvesAvecAdresses, sans résolution d'identifiant."""

    uai: str = None
    school_year: int = None
    # Ni l'un ni l'autre n'est persisté (voir wizard_eleves_import.py) : affichés tels quels dans
    # l'écran d'analyse pour que l'utilisateur distingue deux exports faits à des dates
    # différentes — SIECLE ne les republie pas d'un export à l'autre.
    date_export: str = None
    horodatage: str = None
    students: list = field(default_factory=list)

    def counts(self) -> dict:
        return {"students": len(self.students)}


@dataclass
class ResponsablesFlux:
    """Contenu exploitable du fichier ResponsablesAvecAdresses, sans résolution d'identifiant."""

    uai: str = None
    school_year: int = None
    date_export: str = None
    horodatage: str = None
    # Indexés par identifiant SIECLE (PERSONNE_ID/ADRESSE_ID) : c'est ainsi que RESPONSABLE les
    # référence, une recherche O(1) évite de reparcourir la liste à chaque lien élève-responsable.
    persons: dict = field(default_factory=dict)
    addresses: dict = field(default_factory=dict)
    # Une ligne par RESPONSABLE : un même PERSONNE_ID y apparaît une fois par enfant dans le cas
    # d'une fratrie (voir FORMATS_JUSTIFICATION.md côté GEPI) — pas une anomalie à dédoublonner.
    links: list = field(default_factory=list)

    def counts(self) -> dict:
        return {"persons": len(self.persons), "links": len(self.links)}


def _parse_root(content: bytes, expected_tag: str, expected_label: str):
    try:
        root = ET.fromstring(content)
    except (ParseError, DefusedXmlException) as exc:
        raise ElevesFluxError(f"Le fichier n'est pas un document XML valide : {exc}") from exc

    tag = root.tag.upper()
    if tag == expected_tag:
        return root
    if tag in _KNOWN_SIECLE_ROOTS:
        raise ElevesFluxError(
            f"Ce fichier est {_KNOWN_SIECLE_ROOTS[tag]}, pas {expected_label}. Déposez le bon "
            f"export XML SIECLE (Exploitation > Exports standard > Exports XML générique)."
        )
    raise ElevesFluxError(
        f"Ce fichier n'est pas {expected_label} : sa racine est « {root.tag} » au lieu de "
        f"« {expected_tag} »."
    )


def _parse_parametres(root, flux):
    for parametres in root.iter("PARAMETRES"):
        flux.date_export = _text(parametres, "DATE_EXPORT")
        flux.horodatage = _text(parametres, "HORODATAGE")
        uaj = _text(parametres, "UAJ")
        if uaj:
            flux.uai = uaj
        annee = _text(parametres, "ANNEE_SCOLAIRE")
        if annee and annee.isdigit():
            flux.school_year = int(annee)
        break


def _check_parametres(flux):
    if not flux.uai:
        raise ElevesFluxError(
            "Le fichier ne porte aucun code établissement (PARAMETRES/UAJ). Impossible de "
            "vérifier qu'il concerne bien cette base."
        )
    if not flux.school_year:
        raise ElevesFluxError(
            "Le fichier ne porte aucune année scolaire (PARAMETRES/ANNEE_SCOLAIRE). Impossible "
            "de vérifier qu'il concerne bien l'année de cette base."
        )


def parse_eleves(content: bytes) -> ElevesFlux:
    """Analyse ElevesAvecAdresses.xml. Lève ElevesFluxError si le document n'en est pas un."""
    root = _parse_root(content, ELEVES_ROOT_TAG, "un export « Élèves avec adresses »")
    flux = ElevesFlux()
    _parse_parametres(root, flux)

    # STRUCTURES_ELEVE : la division (TYPE_STRUCTURE=D, une seule attendue) et les groupes
    # (TYPE_STRUCTURE=G, zéro ou plusieurs) de chaque élève.
    structures_par_eleve = {}
    for structures_eleve in root.iter("STRUCTURES_ELEVE"):
        eleve_id = (structures_eleve.get("ELEVE_ID") or "").strip()
        if not eleve_id:
            continue
        division_code = None
        group_codes = []
        for structure in structures_eleve.findall("STRUCTURE"):
            code = _text(structure, "CODE_STRUCTURE")
            type_structure = (_text(structure, "TYPE_STRUCTURE") or "").strip().upper()
            if not code:
                continue
            if type_structure == "D":
                division_code = code
            elif type_structure == "G":
                group_codes.append(code)
            # Toute autre valeur (ou absente) est ignorée : GEPI fait de même, voir
            # FORMATS_JUSTIFICATION.md §2.7 — un élève rattaché à rien plutôt qu'un rejet.
        structures_par_eleve[eleve_id] = {"division_code": division_code, "group_codes": group_codes}

    options_par_eleve = {}
    for option in root.iter("OPTION"):
        eleve_id = (option.get("ELEVE_ID") or "").strip()
        if not eleve_id:
            continue
        lignes = options_par_eleve.setdefault(eleve_id, [])
        for options_eleve in option.findall("OPTIONS_ELEVE"):
            code_matiere = _text(options_eleve, "CODE_MATIERE")
            if not code_matiere:
                continue
            lignes.append({
                "num_option": _text(options_eleve, "NUM_OPTION"),
                "election_code": _text(options_eleve, "CODE_MODALITE_ELECT"),
                "subject_code": code_matiere,
            })

    for eleve in root.iter("ELEVE"):
        eleve_id = (eleve.get("ELEVE_ID") or "").strip()
        if not eleve_id:
            continue
        structures = structures_par_eleve.get(eleve_id, {"division_code": None, "group_codes": []})
        scolarite = eleve.find("SCOLARITE_AN_DERNIER")
        flux.students.append({
            "eleve_id": eleve_id,
            "id_national": _text(eleve, "ID_NATIONAL"),
            "ine_bea": _text(eleve, "INE_BEA"),
            "elenoet": _text(eleve, "ELENOET"),
            # NOM_USAGE prévaut sur NOM (repli), même arbitrage que INDIVIDU côté STS — voir
            # sts_flux._parse_individus et FORMATS_JUSTIFICATION.md §5.4.
            "last_name": _first_label(eleve, "NOM_USAGE", "NOM"),
            "birth_last_name": _text(eleve, "NOM_DE_FAMILLE"),
            "first_name": _text(eleve, "PRENOM"),
            "birth_date": _text(eleve, "DATE_NAISS"),
            "doublement": _text(eleve, "DOUBLEMENT"),
            "entry_date": _text(eleve, "DATE_ENTREE"),
            "exit_date": _text(eleve, "DATE_SORTIE"),
            "regime_code": _text(eleve, "CODE_REGIME"),
            "exit_reason_code": _text(eleve, "CODE_MOTIF_SORTIE"),
            "sexe": _text(eleve, "CODE_SEXE"),
            "birth_city_insee_code": _text(eleve, "CODE_COMMUNE_INSEE_NAISS"),
            "mef_code": _text(eleve, "CODE_MEF"),
            "division_code": structures["division_code"],
            "group_codes": structures["group_codes"],
            "last_year": _parse_scolarite_an_dernier(scolarite) if scolarite is not None else None,
            "options": options_par_eleve.get(eleve_id, []),
        })

    _check_parametres(flux)
    return flux


def _parse_scolarite_an_dernier(scolarite) -> dict:
    return {
        "level": _text(scolarite, "CODE_STRUCTURE"),
        "rne_code": _text(scolarite, "CODE_RNE"),
        "sigle": _text(scolarite, "SIGLE"),
        "denom_princ": _text(scolarite, "DENOM_PRINC"),
        "denom_compl": _text(scolarite, "DENOM_COMPL"),
        "address_line1": _text(scolarite, "LIGNE1_ADRESSE"),
        "address_line2": _text(scolarite, "LIGNE2_ADRESSE"),
        "address_line3": _text(scolarite, "LIGNE3_ADRESSE"),
        "address_line4": _text(scolarite, "LIGNE4_ADRESSE"),
        "po_box": _text(scolarite, "BOITE_POSTALE"),
        "email": _text(scolarite, "MEL"),
        "phone": _text(scolarite, "TELEPHONE"),
        "city_insee_code": _text(scolarite, "CODE_COMMUNE_INSEE"),
        "city_name": _text(scolarite, "LL_COMMUNE_INSEE"),
    }


def parse_responsables(content: bytes) -> ResponsablesFlux:
    """Analyse ResponsablesAvecAdresses.xml. Lève ElevesFluxError si le document n'en est pas un."""
    root = _parse_root(content, RESPONSABLES_ROOT_TAG, "un export « Responsables avec adresses »")
    flux = ResponsablesFlux()
    _parse_parametres(root, flux)

    for personne in root.iter("PERSONNE"):
        personne_id = (personne.get("PERSONNE_ID") or "").strip()
        if not personne_id:
            continue
        flux.persons[personne_id] = {
            "last_name": _first_label(personne, "NOM_USAGE", "NOM"),
            "birth_last_name": _text(personne, "NOM_DE_FAMILLE"),
            "first_name": _text(personne, "PRENOM"),
            "civilite": _text(personne, "LC_CIVILITE"),
            "personal_phone": _text(personne, "TEL_PERSONNEL"),
            "mobile_phone": _text(personne, "TEL_PORTABLE"),
            "professional_phone": _text(personne, "TEL_PROFESSIONNEL"),
            "email": _text(personne, "MEL"),
            "accepts_sms": _text(personne, "ACCEPTE_SMS"),
            "adresse_id": _text(personne, "ADRESSE_ID"),
            "job_code": _text(personne, "CODE_PROFESSION"),
            "communication_by_address": _text(personne, "COMMUNICATION_ADRESSE"),
        }

    for adresse in root.iter("ADRESSE"):
        adresse_id = (adresse.get("ADRESSE_ID") or "").strip()
        if not adresse_id:
            continue
        flux.addresses[adresse_id] = {
            "address_line1": _text(adresse, "LIGNE1_ADRESSE"),
            "address_line2": _text(adresse, "LIGNE2_ADRESSE"),
            "address_line3": _text(adresse, "LIGNE3_ADRESSE"),
            "address_line4": _text(adresse, "LIGNE4_ADRESSE"),
            "zip_code": _text(adresse, "CODE_POSTAL"),
            "country_name": _text(adresse, "LL_PAYS"),
            "department_code": _text(adresse, "CODE_DEPARTEMENT"),
            "postal_label": _text(adresse, "LIBELLE_POSTAL"),
            "foreign_city": _text(adresse, "COMMUNE_ETRANGERE"),
        }

    for responsable in root.iter("RESPONSABLE"):
        eleve_id = _text(responsable, "ELEVE_ID")
        personne_id = _text(responsable, "PERSONNE_ID")
        if not (eleve_id and personne_id):
            continue
        flux.links.append({
            "eleve_id": eleve_id,
            "personne_id": personne_id,
            "resp_legal_code": _text(responsable, "RESP_LEGAL"),
            "relative_link_code": _text(responsable, "CODE_PARENTE"),
            "responsibility_level": _text(responsable, "NIVEAU_RESPONSABILITE"),
            "pays_school_fees": _text(responsable, "PAIE_FRAIS_SCOLAIRES"),
            "resp_financier": _text(responsable, "RESP_FINANCIER"),
            "pers_paiement": _text(responsable, "PERS_PAIMENT"),
            "pers_contact": _text(responsable, "PERS_CONTACT"),
        })

    _check_parametres(flux)
    return flux

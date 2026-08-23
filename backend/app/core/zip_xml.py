"""
Décodage d'un champ binaire pouvant être un XML brut ou un .zip contenant un XML.

Utilisé par le wizard d'import élèves/responsables (SIECLE dépose souvent son export XML dans un
.zip — voir les manuels comparés, `ExportXML_ElevesAvecAdresses.zip`). `sts_flux.py`/
`wizard_sts_import.py` n'a jamais eu ce besoin (le fichier `sts_emp` de STS-web est toujours déposé
nu) et reste inchangé : ce module est propre au nouveau wizard.
"""
import io
import zipfile

from backend.app.core.upload_limits import assert_within_limit

ZIP_MAGIC = b"PK\x03\x04"
# Défense contre un .zip à des milliers d'entrées minuscules (l'équivalent, pour une archive, du
# risque « billion laughs » que defusedxml écarte côté XML — voir sts_flux.py).
_MAX_ZIP_ENTRIES = 50


def extract_xml(data: bytes, filename_hint: str, label: str) -> bytes:
    """
    Si `data` est un .zip, retourne le contenu du membre XML dont le nom contient `filename_hint`
    (insensible à la casse) — un export SIECLE zippé peut contenir plusieurs fichiers
    (Nomenclature.xml, Communs.xml...) dans la même archive. À défaut de correspondance, retient
    l'unique membre .xml du zip s'il n'y en a qu'un. Sinon, `data` est retourné tel quel (déjà du
    XML brut).

    Chaque membre extrait repasse par `assert_within_limit` : la taille déclarée par le zip n'est
    pas une garantie, seuls les octets réellement lus comptent — comme pour tout fichier déposé.
    """
    if data[:4] != ZIP_MAGIC:
        return data

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{label} : le fichier .zip est illisible.") from exc

    membres = [i for i in archive.infolist() if not i.is_dir() and i.filename.lower().endswith(".xml")]
    if not membres:
        raise ValueError(f"{label} : le fichier .zip ne contient aucun fichier .xml.")
    if len(membres) > _MAX_ZIP_ENTRIES:
        raise ValueError(f"{label} : le fichier .zip contient trop de membres ({len(membres)}).")

    cible = next((m for m in membres if filename_hint.lower() in m.filename.lower()), None)
    if cible is None:
        if len(membres) > 1:
            noms = ", ".join(m.filename for m in membres)
            raise ValueError(
                f"{label} : ce .zip contient plusieurs fichiers XML ({noms}) et aucun ne "
                f"correspond à « {filename_hint} ». Déposez-le seul dans son propre .zip, ou "
                f"déposez directement le fichier XML."
            )
        cible = membres[0]

    return assert_within_limit(archive.read(cible), label)

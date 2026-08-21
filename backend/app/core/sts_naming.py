"""
Règles de nommage des structures (divisions et groupes) imposées par STS-web.

Deux règles, toutes deux relevées dans la documentation des logiciels du marché :

- **Longueur et jeu de caractères des groupes.** EDT « tronque le nom du groupe s'il compte
  plus de 8 caractères, et supprime tous les caractères non autorisés » ; UnDeuxTEMPS classe
  « nom de groupe ou regroupement non conforme (contient des caractères spéciaux) » parmi ses
  points bloquants à l'export. Le jeu exact n'est publié nulle part : on retient l'alphanumérique
  plus le point, le tiret et le souligné, les codes de groupe réels observés étant de la forme
  `6LV1.ALL` ou `3AGL1.GR.1`.

- **Unicité dans un espace de noms commun.** UnDeuxTEMPS : « Toutes les classes, groupes et
  regroupements n'ont pas un nom unique » est un point bloquant. Une division et un groupe ne
  peuvent donc pas porter le même identifiant, alors même qu'ils vivent dans deux tables
  distinctes — d'où ce module partagé plutôt qu'une règle dupliquée des deux côtés.

Côté Klepsydrix, l'identifiant de structure est `Division.code` et `Group.name` : le groupe n'a
pas de champ `code`, c'est son nom généré (`compute_group_name`, de la forme `6GMATHS1`) qui joue
ce rôle et qui part dans `GROUPE/@CODE`.
"""
import re

# Longueur maximale d'un nom de groupe accepté par STS-web.
STS_GROUP_NAME_MAX_LENGTH = 8

# Caractères autorisés dans un identifiant de structure.
_STS_ALLOWED_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_STS_FORBIDDEN_PATTERN = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_sts_code(value: str, max_length: int = STS_GROUP_NAME_MAX_LENGTH) -> str:
    """
    Rend un identifiant conforme : caractères interdits supprimés, puis troncature. C'est la
    règle d'EDT, appliquée ici à la génération plutôt qu'à l'export — mieux vaut un nom conforme
    dès sa création qu'une troncature silencieuse au moment de la remontée.
    """
    return _STS_FORBIDDEN_PATTERN.sub("", value or "")[:max_length]


def validate_sts_group_name(value: str):
    """Format d'un nom de groupe. Lève ValueError, ne corrige rien."""
    if not value:
        raise ValueError("Le nom d'un groupe est obligatoire.")
    if len(value) > STS_GROUP_NAME_MAX_LENGTH:
        raise ValueError(
            f"Le nom d'un groupe ne peut pas dépasser {STS_GROUP_NAME_MAX_LENGTH} caractères "
            f"(STS-web refuse au-delà) : « {value} » en compte {len(value)}."
        )
    if not _STS_ALLOWED_PATTERN.match(value):
        interdits = "".join(sorted(set(_STS_FORBIDDEN_PATTERN.findall(value))))
        raise ValueError(
            f"Le nom d'un groupe ne peut contenir que des lettres, des chiffres, un point, "
            f"un tiret ou un souligné — caractère(s) refusé(s) par STS-web : « {interdits} »."
        )


def check_structure_name_is_unique(db, value: str, *, exclude_group_id=None, exclude_division_id=None):
    """
    Unicité de l'identifiant dans l'espace de noms commun aux divisions et aux groupes.
    Appelée depuis les deux modèles, avec l'identifiant de l'instance courante à exclure.
    """
    from backend.app.models.division import Division
    from backend.app.models.group import Group

    division_query = db.query(Division).filter(Division.code == value)
    if exclude_division_id is not None:
        division_query = division_query.filter(Division.id != exclude_division_id)
    if division_query.first():
        raise ValueError(
            f"« {value} » est déjà le code d'une classe. STS-web exige que classes, groupes et "
            f"regroupements portent des identifiants tous distincts."
        )

    group_query = db.query(Group).filter(Group.name == value)
    if exclude_group_id is not None:
        group_query = group_query.filter(Group.id != exclude_group_id)
    if group_query.first():
        raise ValueError(
            f"« {value} » est déjà le nom d'un groupe. STS-web exige que classes, groupes et "
            f"regroupements portent des identifiants tous distincts."
        )

"""
Moteur de droits façon Odoo (voir architecture.md, modèle `IrModelAccess`) : résolution des groupes
effectifs d'un utilisateur (héritage `implied_groups`), compilation du champ `domain` (notation
Odoo, listes de tuples/opérateurs logiques préfixés) en clause SQLAlchemy, et calcul de l'accès
effectif à un modèle pour une opération donnée (read/write/create/unlink).

Compilateur récursif classique (dict/tuple -> clause SQLAlchemy), pas un nouveau sous-système : la
seule partie non triviale est la traversée de chemin pointé (`class_parts.students.user_id`), un
`.any(...)` (collection) ou `.has(...)` (many-to-one) imbriqué par segment.
"""
import json
from sqlalchemy import and_, or_, not_, inspect


def resolve_effective_group_objects(user) -> set:
    """Tous les ResGroup de l'utilisateur, y compris hérités via implied_groups (parcours en largeur)."""
    if user is None:
        return set()
    visited = {}
    stack = list(user.groups)
    while stack:
        group = stack.pop()
        if group.id in visited:
            continue
        visited[group.id] = group
        stack.extend(group.implied_groups)
    return set(visited.values())


def resolve_effective_groups(user) -> set:
    """IDs de tous les groupes effectifs de l'utilisateur — voir resolve_effective_group_objects()."""
    return {g.id for g in resolve_effective_group_objects(user)}


# Valeurs magiques utilisables comme `value` dans un domaine (notation Odoo) — résolues contre
# l'utilisateur courant au moment de la compilation, jamais évaluées comme du code Python arbitraire
# (contrairement à Odoo, qui utilise eval() dans un espace de noms contrôlé).
_MAGIC_VALUES = {
    "user.id": lambda user: user.id,
    "user.group_ids": lambda user: list(resolve_effective_groups(user)),
    "user.teacher.id": lambda user: user.teacher.id if getattr(user, "teacher", None) else None,
    "user.student.id": lambda user: user.student.id if getattr(user, "student", None) else None,
    "user.non_teaching_staff.id": lambda user: user.non_teaching_staff.id if getattr(user, "non_teaching_staff", None) else None,
    "user.parent.id": lambda user: user.parent.id if getattr(user, "parent", None) else None,
}


def _resolve_value(value, user):
    if isinstance(value, str) and value in _MAGIC_VALUES:
        return _MAGIC_VALUES[value](user)
    return value


_OPERATORS = {
    "=": lambda col, v: col == v,
    "!=": lambda col, v: col != v,
    ">": lambda col, v: col > v,
    "<": lambda col, v: col < v,
    ">=": lambda col, v: col >= v,
    "<=": lambda col, v: col <= v,
    "in": lambda col, v: col.in_(v),
    "not in": lambda col, v: ~col.in_(v),
    "like": lambda col, v: col.like(f"%{v}%"),
    "ilike": lambda col, v: col.ilike(f"%{v}%"),
}


def _compile_path(model, parts: list, op: str, value):
    if len(parts) == 1:
        column = getattr(model, parts[0], None)
        if column is None:
            raise ValueError(f"« {parts[0]} » n'existe pas sur {model.__name__} (chemin de domaine invalide).")
        if op not in _OPERATORS:
            raise ValueError(f"Opérateur de domaine non supporté : {op}")
        return _OPERATORS[op](column, value)

    head, *rest = parts
    mapper = inspect(model)
    if head not in mapper.relationships:
        raise ValueError(f"« {head} » n'est pas une relation de {model.__name__} (chemin de domaine invalide).")
    rel = mapper.relationships[head]
    target_cls = rel.mapper.class_
    sub_clause = _compile_path(target_cls, rest, op, value)
    attr = getattr(model, head)
    return attr.any(sub_clause) if rel.uselist else attr.has(sub_clause)


def _compile_term(model, domain: list, pos: int, user):
    token = domain[pos]
    if token == "&":
        left, pos = _compile_term(model, domain, pos + 1, user)
        right, pos = _compile_term(model, domain, pos, user)
        return and_(left, right), pos
    if token == "|":
        left, pos = _compile_term(model, domain, pos + 1, user)
        right, pos = _compile_term(model, domain, pos, user)
        return or_(left, right), pos
    if token == "!":
        operand, pos = _compile_term(model, domain, pos + 1, user)
        return not_(operand), pos
    field_path, op, value = token
    value = _resolve_value(value, user)
    return _compile_path(model, field_path.split("."), op, value), pos + 1


def compile_domain(model, domain_json: str, user):
    """`domain_json` : colonne `IrModelAccess.domain` (JSON texte) — None/vide = aucune restriction."""
    if not domain_json:
        return None
    domain = json.loads(domain_json)
    if not domain:
        return None
    clauses = []
    pos = 0
    while pos < len(domain):
        clause, pos = _compile_term(model, domain, pos, user)
        clauses.append(clause)
    result = clauses[0]
    for extra in clauses[1:]:
        result = and_(result, extra)
    return result


_PERM_COLUMNS = {"read": "perm_read", "write": "perm_write", "create": "perm_create", "unlink": "perm_unlink"}


def access_rows_for(db, model, user, operation: str) -> list:
    """
    Lignes `ir_model_access` qui accordent `operation` à l'utilisateur pour ce modèle, tous
    groupes confondus (héritage `implied_groups` compris). Liste vide = aucun droit — c'est la
    garde-fou par défaut : sans aucune ligne pour un modèle, personne n'y accède (voir
    architecture.md).
    """
    from backend.app.models.access import IrModelAccess

    group_ids = resolve_effective_groups(user)
    if not group_ids:
        return []
    perm_attr = getattr(IrModelAccess, _PERM_COLUMNS[operation])
    return db.query(IrModelAccess).filter(
        IrModelAccess.model == model.__tablename__,
        IrModelAccess.group_id.in_(group_ids),
        perm_attr == True,  # noqa: E712 (comparaison SQLAlchemy, pas Python)
    ).all()


def get_display_name_unchecked(db, model, obj_id: int):
    """
    Lecture privilégiée du SEUL display_name d'un enregistrement — utilisée pour résoudre le
    libellé d'une relation que l'utilisateur courant n'a pas forcément le droit de lire dans son
    intégralité (voir architecture.md, "display_name d'une relation non lisible" : sans elle, tout
    formulaire/liste/widget relation casse pour un profil non-admin dès qu'un droit restrictif
    existe). N'ÉLARGIT RIEN d'autre — n'importe quel autre champ de l'objet reste soumis au moteur
    de droits normal. Retourne None si l'enregistrement n'existe pas, jamais une exception.
    """
    obj = db.get(model, obj_id)
    return obj.display_name if obj is not None else None


def access_domain_clause(db, model, user, operation: str):
    """
    (has_access, clause) :
    - has_access=False : aucun droit du tout — l'appelant doit refuser l'opération.
    - clause=None : droit total, aucune restriction par enregistrement.
    - clause=<expression SQLAlchemy> : restreint aux lignes qui la satisfont — OR de toutes les
      lignes qualifiantes (une seule ligne SANS domaine suffit à lever toute restriction, cohérent
      avec la combinaison OR entre lignes ir_model_access).
    """
    rows = access_rows_for(db, model, user, operation)
    if not rows:
        return False, None
    domain_clauses = []
    for row in rows:
        clause = compile_domain(model, row.domain, user)
        if clause is None:
            return True, None
        domain_clauses.append(clause)
    return True, or_(*domain_clauses)

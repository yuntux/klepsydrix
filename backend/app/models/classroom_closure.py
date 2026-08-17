from sqlalchemy import Table, Column, Integer, ForeignKey, select, delete, insert
from sqlalchemy.orm import Session
from backend.app.models.base import Base

# Closure table pour l'arbre des groupes de salles (Classroom.parent_classroom_id) — une Table Core,
# pas une classe ORM mappée : reste invisible à l'API CRUD générique (/api/generic/*), qui découvre
# ses ressources via Base.registry.mappers, jamais une Table brute (même raisonnement que
# exclusive_mode_state). Stocke TOUTES les paires ancêtre/descendant (pas seulement parent direct),
# avec la profondeur, pour éviter une CTE récursive à chaque lecture.
classroom_closure = Table(
    "classroom_closure",
    Base.metadata,
    Column("ancestor_id", Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True),
    Column("descendant_id", Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True),
    Column("depth", Integer, nullable=False),
)


def ensure_reflexive_row(db: Session, classroom_id: int) -> None:
    """À la création d'une salle : garantit la ligne réflexive (id, id, 0), condition pour que
    toutes les fonctions ci-dessous (notamment leaf_classroom_ids_under) fonctionnent même pour
    une salle qui n'a jamais eu de parent ni d'enfant."""
    exists = db.execute(
        select(classroom_closure.c.ancestor_id).where(
            classroom_closure.c.ancestor_id == classroom_id,
            classroom_closure.c.descendant_id == classroom_id,
        )
    ).first()
    if exists is None:
        db.execute(insert(classroom_closure).values(ancestor_id=classroom_id, descendant_id=classroom_id, depth=0))


def detect_cycle(db: Session, node_id: int, candidate_parent_id: int) -> bool:
    """`candidate_parent_id` est-il déjà descendant de `node_id` ? Si oui, le faire parent de
    `node_id` créerait un cycle (topologie d'arbre stricte requise, jamais un graphe)."""
    if node_id == candidate_parent_id:
        return True
    row = db.execute(
        select(classroom_closure.c.ancestor_id).where(
            classroom_closure.c.ancestor_id == node_id,
            classroom_closure.c.descendant_id == candidate_parent_id,
        )
    ).first()
    return row is not None


def reparent_subtree(db: Session, node_id: int, new_parent_id: "int | None") -> None:
    """Algorithme standard « closure table move subtree », en deux temps :
    1. Détacher node_id (et tout son sous-arbre) de ses anciens ancêtres stricts.
    2. Si new_parent_id est fourni, rattacher node_id (et son sous-arbre) sous ce nouveau parent,
       en recomposant les profondeurs à partir des ancêtres de new_parent_id.
    Appelée à chaque changement de Classroom.parent_classroom_id (y compris première affectation
    et remise à NULL) — voir Classroom._validate_and_sync_classroom_tree.
    """
    ensure_reflexive_row(db, node_id)

    # 1. Détachement : supprime toute ligne reliant un ancêtre STRICT de node_id à un descendant
    # (au sens large, node_id inclus) de node_id.
    descendant_ids_subq = select(classroom_closure.c.descendant_id).where(
        classroom_closure.c.ancestor_id == node_id
    )
    ancestor_ids_subq = select(classroom_closure.c.ancestor_id).where(
        classroom_closure.c.descendant_id == node_id,
        classroom_closure.c.ancestor_id != node_id,
    )
    db.execute(
        delete(classroom_closure).where(
            classroom_closure.c.descendant_id.in_(descendant_ids_subq),
            classroom_closure.c.ancestor_id.in_(ancestor_ids_subq),
        )
    )

    if new_parent_id is None:
        return

    # 2. Rattachement : pour chaque ancêtre de new_parent_id (lui inclus) et chaque descendant de
    # node_id (lui inclus), insère une ligne de profondeur cumulée.
    ancestors_of_new_parent = db.execute(
        select(classroom_closure.c.ancestor_id, classroom_closure.c.depth).where(
            classroom_closure.c.descendant_id == new_parent_id
        )
    ).all()
    descendants_of_node = db.execute(
        select(classroom_closure.c.descendant_id, classroom_closure.c.depth).where(
            classroom_closure.c.ancestor_id == node_id
        )
    ).all()

    rows_to_insert = [
        {
            "ancestor_id": ancestor_row.ancestor_id,
            "descendant_id": descendant_row.descendant_id,
            "depth": ancestor_row.depth + descendant_row.depth + 1,
        }
        for ancestor_row in ancestors_of_new_parent
        for descendant_row in descendants_of_node
    ]
    if rows_to_insert:
        db.execute(insert(classroom_closure), rows_to_insert)


def is_descendant_or_equal(db: Session, ancestor_id: int, node_id: int) -> bool:
    """`node_id` est-il `ancestor_id` lui-même, ou un de ses descendants (à travers d'éventuels
    sous-groupes imbriqués) ? Utilisé par la cascade de décrémentation quantité-consciente
    (CourseClassroomRequirement) pour vérifier qu'une salle précise ou un sous-groupe rattaché à
    un enfant appartient bien au groupe déjà déclaré sur le parent, pas juste une coïncidence."""
    if ancestor_id == node_id:
        return True
    row = db.execute(
        select(classroom_closure.c.ancestor_id).where(
            classroom_closure.c.ancestor_id == ancestor_id,
            classroom_closure.c.descendant_id == node_id,
        )
    ).first()
    return row is not None


def leaf_classroom_ids_under(db: Session, group_id: int) -> list[int]:
    """Toutes les salles-feuilles (sans enfant) descendantes de group_id, group_id lui-même
    inclus s'il est déjà une feuille — descend récursivement à travers les sous-groupes imbriqués
    via la closure table (requête indexée, pas de récursion applicative)."""
    descendant_ids_subq = select(classroom_closure.c.descendant_id).where(
        classroom_closure.c.ancestor_id == group_id
    )
    has_child_subq = select(classroom_closure.c.ancestor_id).where(
        classroom_closure.c.depth == 1
    )
    rows = db.execute(
        select(classroom_closure.c.descendant_id).where(
            classroom_closure.c.descendant_id.in_(descendant_ids_subq),
            classroom_closure.c.descendant_id.notin_(has_child_subq),
        ).distinct()
    ).all()
    return [r.descendant_id for r in rows]

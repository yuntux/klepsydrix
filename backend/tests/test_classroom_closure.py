"""
Tests dédiés à classroom_closure.py (plan salles §1.2) — la closure table qui maintient l'arbre
des groupes de salles (Classroom.parent_classroom_id) à jour, et aux @constrains de Classroom qui
s'appuient dessus (détection de cycle, homogénéité de capacité, nettoyage silencieux de
ref_classroom_type_id). Le plan qualifiait explicitement cette brique de fondation « à blinder
avant tout le reste » : tout (COURSE_PLACEMENT, CLASSROOM_ASSIGNMENT, la cascade
CourseClassroomRequirement) s'appuie sur leaf_classroom_ids_under/is_descendant_or_equal — une
closure table incorrecte casserait silencieusement tout ce qui est construit dessus.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker, Session
from backend.app.models.base import Base
from backend.app.models.school import School
from backend.app.models.classroom import Classroom
from backend.app.models.ref_classroom_type import RefClassroomType
from backend.app.models.classroom_closure import (
    classroom_closure, detect_cycle, is_descendant_or_equal, leaf_classroom_ids_under,
)
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        school = School.create(db, {"uai": "1234567A", "name": "Lycée Test"})
        db.commit()
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _closure_rows(db, ancestor_id=None, descendant_id=None):
    query = select(classroom_closure)
    if ancestor_id is not None:
        query = query.where(classroom_closure.c.ancestor_id == ancestor_id)
    if descendant_id is not None:
        query = query.where(classroom_closure.c.descendant_id == descendant_id)
    return {(r.ancestor_id, r.descendant_id, r.depth) for r in db.execute(query).all()}


# =====================================================================================
# Insertion / attachement — cas de base
# =====================================================================================

def test_reflexive_row_created_on_classroom_creation(db_session: Session):
    school = db_session.query(School).first()
    room = Classroom.create(db_session, {"code": "R1", "name": "Salle 1", "school_id": school.id})
    db_session.commit()

    assert _closure_rows(db_session, ancestor_id=room.id) == {(room.id, room.id, 0)}


def test_simple_attachment_creates_closure_row_at_depth_one(db_session: Session):
    school = db_session.query(School).first()
    group = Classroom.create(db_session, {"code": "GRP", "name": "Groupe", "school_id": school.id})
    room = Classroom.create(db_session, {"code": "R1", "name": "Salle 1", "school_id": school.id, "parent_classroom_id": group.id})
    db_session.commit()

    assert _closure_rows(db_session, descendant_id=room.id) == {(room.id, room.id, 0), (group.id, room.id, 1)}


def test_nested_attachment_creates_closure_rows_at_all_depths(db_session: Session):
    """root -> mid -> leaf (3 niveaux) : leaf doit être descendant de root ET de mid, à des
    profondeurs différentes (2 et 1) — pas seulement de son parent direct."""
    school = db_session.query(School).first()
    root = Classroom.create(db_session, {"code": "ROOT", "name": "Root", "school_id": school.id})
    mid = Classroom.create(db_session, {"code": "MID", "name": "Mid", "school_id": school.id, "parent_classroom_id": root.id})
    leaf = Classroom.create(db_session, {"code": "LEAF", "name": "Leaf", "school_id": school.id, "parent_classroom_id": mid.id})
    db_session.commit()

    assert _closure_rows(db_session, descendant_id=leaf.id) == {
        (leaf.id, leaf.id, 0), (mid.id, leaf.id, 1), (root.id, leaf.id, 2),
    }
    assert _closure_rows(db_session, descendant_id=mid.id) == {(mid.id, mid.id, 0), (root.id, mid.id, 1)}


# =====================================================================================
# Ré-attachement / détachement
# =====================================================================================

def test_reparent_deep_subtree_removes_stale_and_creates_new_rows(db_session: Session):
    """Déplace tout le sous-arbre mid->leaf de root vers other_root : les anciennes lignes
    (root,mid)/(root,leaf) doivent disparaître, les nouvelles (other_root,mid)/(other_root,leaf)
    apparaître, et la relation interne au sous-arbre (mid,leaf) doit rester intacte."""
    school = db_session.query(School).first()
    root = Classroom.create(db_session, {"code": "ROOT2", "name": "Root2", "school_id": school.id})
    other_root = Classroom.create(db_session, {"code": "OROOT2", "name": "OtherRoot2", "school_id": school.id})
    mid = Classroom.create(db_session, {"code": "MID2", "name": "Mid2", "school_id": school.id, "parent_classroom_id": root.id})
    leaf = Classroom.create(db_session, {"code": "LEAF2", "name": "Leaf2", "school_id": school.id, "parent_classroom_id": mid.id})
    db_session.commit()

    mid.update(db_session, {"parent_classroom_id": other_root.id})
    db_session.commit()

    assert _closure_rows(db_session, ancestor_id=root.id, descendant_id=mid.id) == set()
    assert _closure_rows(db_session, ancestor_id=root.id, descendant_id=leaf.id) == set()
    assert _closure_rows(db_session, ancestor_id=other_root.id, descendant_id=mid.id) == {(other_root.id, mid.id, 1)}
    assert _closure_rows(db_session, ancestor_id=other_root.id, descendant_id=leaf.id) == {(other_root.id, leaf.id, 2)}
    # La relation interne au sous-arbre déplacé n'a pas à être recalculée, elle est inchangée.
    assert _closure_rows(db_session, ancestor_id=mid.id, descendant_id=leaf.id) == {(mid.id, leaf.id, 1)}
    # Aucune ligne orpheline : le nombre total de lignes doit rester cohérent (pas de doublon).
    all_rows_for_leaf = _closure_rows(db_session, descendant_id=leaf.id)
    assert all_rows_for_leaf == {(leaf.id, leaf.id, 0), (mid.id, leaf.id, 1), (other_root.id, leaf.id, 2)}


def test_detach_makes_node_root_again(db_session: Session):
    school = db_session.query(School).first()
    group = Classroom.create(db_session, {"code": "GRP3", "name": "Groupe3", "school_id": school.id})
    room = Classroom.create(db_session, {"code": "R3", "name": "Salle3", "school_id": school.id, "parent_classroom_id": group.id})
    db_session.commit()

    room.update(db_session, {"parent_classroom_id": None})
    db_session.commit()

    assert _closure_rows(db_session, descendant_id=room.id) == {(room.id, room.id, 0)}
    assert is_descendant_or_equal(db_session, group.id, room.id) is False


# =====================================================================================
# Détection de cycle — topologie d'arbre stricte
# =====================================================================================

def test_cycle_direct_self_parent_rejected(db_session: Session):
    school = db_session.query(School).first()
    room = Classroom.create(db_session, {"code": "R4", "name": "Salle4", "school_id": school.id})
    db_session.commit()

    with pytest.raises(ValueError):
        room.update(db_session, {"parent_classroom_id": room.id})


def test_cycle_indirect_two_levels_rejected(db_session: Session):
    """A -> B (B enfant de A). Tenter de faire de B le parent de A doit être rejeté (créerait un
    cycle A->B->A)."""
    school = db_session.query(School).first()
    a = Classroom.create(db_session, {"code": "A5", "name": "A5", "school_id": school.id})
    b = Classroom.create(db_session, {"code": "B5", "name": "B5", "school_id": school.id, "parent_classroom_id": a.id})
    db_session.commit()

    assert detect_cycle(db_session, a.id, b.id) is True
    with pytest.raises(ValueError):
        a.update(db_session, {"parent_classroom_id": b.id})


def test_cycle_indirect_four_levels_rejected(db_session: Session):
    """A -> B -> C -> D. Tenter de faire de D le parent de A doit être rejeté (cycle sur 4
    niveaux, pas seulement détecté sur le parent direct)."""
    school = db_session.query(School).first()
    a = Classroom.create(db_session, {"code": "A6", "name": "A6", "school_id": school.id})
    b = Classroom.create(db_session, {"code": "B6", "name": "B6", "school_id": school.id, "parent_classroom_id": a.id})
    c = Classroom.create(db_session, {"code": "C6", "name": "C6", "school_id": school.id, "parent_classroom_id": b.id})
    d = Classroom.create(db_session, {"code": "D6", "name": "D6", "school_id": school.id, "parent_classroom_id": c.id})
    db_session.commit()

    assert detect_cycle(db_session, a.id, d.id) is True
    with pytest.raises(ValueError):
        a.update(db_session, {"parent_classroom_id": d.id})

    # Un lien qui ne crée PAS de cycle (D devient parent d'une salle totalement indépendante)
    # doit rester accepté — la détection ne doit pas être sur-sensible.
    unrelated = Classroom.create(db_session, {"code": "E6", "name": "E6", "school_id": school.id})
    db_session.commit()
    assert detect_cycle(db_session, unrelated.id, d.id) is False
    unrelated.update(db_session, {"parent_classroom_id": d.id})
    db_session.commit()
    assert _closure_rows(db_session, ancestor_id=d.id, descendant_id=unrelated.id) == {(d.id, unrelated.id, 1)}


# =====================================================================================
# ref_classroom_type_id — nettoyage silencieux, jamais un rejet (plan salles §1.1/§1.3)
# =====================================================================================

def test_ref_classroom_type_cleared_when_classroom_gains_first_child(db_session: Session):
    school = db_session.query(School).first()
    rtype = RefClassroomType.create(db_session, {"code": "16", "name": "SALLE PHYS&SPORTIVE", "long_name": "Salle d'activités physiques et sportives"})
    db_session.commit()

    room = Classroom.create(db_session, {"code": "TYPED", "name": "Salle typée", "school_id": school.id, "ref_classroom_type_id": rtype.id})
    db_session.commit()
    assert room.ref_classroom_type_id == rtype.id

    # Rattacher un enfant à `room` ne doit jamais échouer pour cette raison : le type est
    # simplement nettoyé.
    Classroom.create(db_session, {"code": "CHILD_OF_TYPED", "name": "Enfant", "school_id": school.id, "parent_classroom_id": room.id})
    db_session.commit()

    db_session.refresh(room)
    assert room.ref_classroom_type_id is None


def test_ref_classroom_type_assignment_silently_ignored_on_existing_group(db_session: Session):
    school = db_session.query(School).first()
    rtype = RefClassroomType.create(db_session, {"code": "18", "name": "SALLE DE MUSIQUE", "long_name": "Salle de musique"})
    db_session.commit()

    group = Classroom.create(db_session, {"code": "ALREADY_GRP", "name": "Déjà groupe", "school_id": school.id})
    Classroom.create(db_session, {"code": "CHILD_ALREADY", "name": "Enfant", "school_id": school.id, "parent_classroom_id": group.id})
    db_session.commit()

    # `group` a déjà un enfant : lui affecter un type ne doit pas échouer, juste ne jamais prendre.
    group.update(db_session, {"ref_classroom_type_id": rtype.id})
    db_session.commit()
    db_session.refresh(group)
    assert group.ref_classroom_type_id is None


# =====================================================================================
# Homogénéité de capacité (plan salles §1.1)
# =====================================================================================

def test_capacity_homogeneity_rejects_mixed_null_and_numeric(db_session: Session):
    school = db_session.query(School).first()
    group = Classroom.create(db_session, {"code": "GRP_HOMO1", "name": "Grp", "school_id": school.id})
    Classroom.create(db_session, {"code": "R_NUM", "name": "R num", "school_id": school.id, "capacity": 30, "parent_classroom_id": group.id})
    db_session.commit()

    with pytest.raises(ValueError):
        Classroom.create(db_session, {"code": "R_NULL", "name": "R null", "school_id": school.id, "capacity": None, "parent_classroom_id": group.id})


def test_capacity_homogeneity_rejects_mismatched_numeric(db_session: Session):
    school = db_session.query(School).first()
    group = Classroom.create(db_session, {"code": "GRP_HOMO2", "name": "Grp", "school_id": school.id})
    Classroom.create(db_session, {"code": "R_30", "name": "R30", "school_id": school.id, "capacity": 30, "parent_classroom_id": group.id})
    db_session.commit()

    with pytest.raises(ValueError):
        Classroom.create(db_session, {"code": "R_25", "name": "R25", "school_id": school.id, "capacity": 25, "parent_classroom_id": group.id})


def test_capacity_homogeneity_accepts_matching_numeric_and_matching_null(db_session: Session):
    school = db_session.query(School).first()
    group_numeric = Classroom.create(db_session, {"code": "GRP_HOMO3", "name": "Grp num", "school_id": school.id})
    Classroom.create(db_session, {"code": "R_30A", "name": "R30a", "school_id": school.id, "capacity": 30, "parent_classroom_id": group_numeric.id})
    db_session.commit()
    Classroom.create(db_session, {"code": "R_30B", "name": "R30b", "school_id": school.id, "capacity": 30, "parent_classroom_id": group_numeric.id})
    db_session.commit()

    group_unlimited = Classroom.create(db_session, {"code": "GRP_HOMO4", "name": "Grp illim", "school_id": school.id})
    Classroom.create(db_session, {"code": "R_NULLA", "name": "Rnulla", "school_id": school.id, "capacity": None, "parent_classroom_id": group_unlimited.id})
    db_session.commit()
    Classroom.create(db_session, {"code": "R_NULLB", "name": "Rnullb", "school_id": school.id, "capacity": None, "parent_classroom_id": group_unlimited.id})
    db_session.commit()  # ne doit lever aucune exception


# =====================================================================================
# leaf_classroom_ids_under
# =====================================================================================

def test_leaf_classroom_ids_under_flat_group(db_session: Session):
    school = db_session.query(School).first()
    group = Classroom.create(db_session, {"code": "GRP_FLAT", "name": "Grp plat", "school_id": school.id})
    l1 = Classroom.create(db_session, {"code": "L_FLAT1", "name": "L1", "school_id": school.id, "parent_classroom_id": group.id})
    l2 = Classroom.create(db_session, {"code": "L_FLAT2", "name": "L2", "school_id": school.id, "parent_classroom_id": group.id})
    db_session.commit()

    assert set(leaf_classroom_ids_under(db_session, group.id)) == {l1.id, l2.id}


def test_leaf_classroom_ids_under_nested_groups(db_session: Session):
    """Un sous-groupe imbriqué ne doit jamais apparaître dans le résultat — seules les
    salles-feuilles réelles, à n'importe quelle profondeur."""
    school = db_session.query(School).first()
    top = Classroom.create(db_session, {"code": "GRP_TOP", "name": "Top", "school_id": school.id})
    direct_leaf = Classroom.create(db_session, {"code": "L_DIRECT", "name": "Direct leaf", "school_id": school.id, "parent_classroom_id": top.id})
    sub = Classroom.create(db_session, {"code": "GRP_SUB", "name": "Sous-groupe", "school_id": school.id, "parent_classroom_id": top.id})
    sub_leaf1 = Classroom.create(db_session, {"code": "L_SUB1", "name": "Sub leaf 1", "school_id": school.id, "parent_classroom_id": sub.id})
    sub_leaf2 = Classroom.create(db_session, {"code": "L_SUB2", "name": "Sub leaf 2", "school_id": school.id, "parent_classroom_id": sub.id})
    db_session.commit()

    result = set(leaf_classroom_ids_under(db_session, top.id))
    assert result == {direct_leaf.id, sub_leaf1.id, sub_leaf2.id}
    assert sub.id not in result


def test_leaf_classroom_ids_under_leaf_room_passed_directly(db_session: Session):
    """Une salle-feuille passée directement (jamais un groupe) : se retourne elle-même — cohérent
    avec le fait qu'une Classroom sans enfant EST une feuille, groupe ou non n'est qu'une question
    de savoir si elle a des enfants au moment de l'appel."""
    school = db_session.query(School).first()
    room = Classroom.create(db_session, {"code": "L_ALONE", "name": "Salle seule", "school_id": school.id})
    db_session.commit()

    assert leaf_classroom_ids_under(db_session, room.id) == [room.id]


# =====================================================================================
# is_descendant_or_equal
# =====================================================================================

def test_is_descendant_or_equal_matrix(db_session: Session):
    school = db_session.query(School).first()
    root = Classroom.create(db_session, {"code": "IDE_ROOT", "name": "Root", "school_id": school.id})
    mid = Classroom.create(db_session, {"code": "IDE_MID", "name": "Mid", "school_id": school.id, "parent_classroom_id": root.id})
    leaf = Classroom.create(db_session, {"code": "IDE_LEAF", "name": "Leaf", "school_id": school.id, "parent_classroom_id": mid.id})
    unrelated = Classroom.create(db_session, {"code": "IDE_UNREL", "name": "Unrelated", "school_id": school.id})
    db_session.commit()

    assert is_descendant_or_equal(db_session, root.id, root.id) is True    # égal
    assert is_descendant_or_equal(db_session, root.id, leaf.id) is True    # descendant profond
    assert is_descendant_or_equal(db_session, mid.id, leaf.id) is True     # descendant direct
    assert is_descendant_or_equal(db_session, leaf.id, root.id) is False   # sens inverse : faux
    assert is_descendant_or_equal(db_session, root.id, unrelated.id) is False  # aucun lien

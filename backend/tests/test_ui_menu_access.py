"""
Tests pour le filtrage de l'arbre ui.json par droits (voir architecture.md, moteur de droits,
"Lot 4bis" filtrage du menu) — backend/app/api/ui_endpoints.py::filter_menu_for_user.
"""
import json
import os
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import School, User, ResGroup, IrModelAccess, SystemSetting
from backend.tests.db_test_utils import make_test_engine
from backend.app.api.ui_endpoints import filter_menu_for_user, validate_menu_ids

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _user_with_access(db, rows):
    """rows: liste de (model, group_name, perm_read, perm_write)."""
    user = User.create(db, {"first_name": "A", "last_name": "A", "email": None})
    for model, group_name, perm_read, perm_write in rows:
        group = db.query(ResGroup).filter(ResGroup.name == group_name).first()
        if not group:
            group = ResGroup.create(db, {"name": group_name})
            group.update(db, {"user_ids": [user.id]})
        IrModelAccess.create(db, {"model": model, "group_id": group.id, "perm_read": perm_read, "perm_write": perm_write})
    return user


_TREE = [
    {"id": "root_schools", "title": "Écoles", "panels": [
        {"id": "p1", "component": "GenericList", "resourceKey": "schools"},
    ]},
    {"id": "root_courses_group", "title": "Cours", "children": [
        {"id": "courses_leaf", "title": "Liste", "panels": [
            {"id": "p2", "component": "GenericList", "resourceKey": "courses"},
        ]},
    ]},
    {"id": "root_pivot", "title": "Pas de resourceKey", "panels": [
        {"id": "p3", "component": "TimetableGrid"},
    ]},
    {"id": "root_action", "title": "Générer", "action": {"resourceKey": "courses", "actionId": "do_it"}},
    {"id": "root_gated", "title": "Réservé Admin", "groups": ["Admin Test"], "panels": [
        {"id": "p4", "component": "GenericList", "resourceKey": "schools"},
    ]},
]


class TestFilterMenuForUser:
    def test_leaf_hidden_without_read_access(self, db_session):
        user = _user_with_access(db_session, [("courses", "Lecteur Cours", True, False)])
        result = filter_menu_for_user(_TREE, db_session, user, set())
        ids = {n["id"] for n in result}
        assert "root_schools" not in ids  # pas de droit sur schools
        assert "root_courses_group" in ids  # a un droit de lecture sur courses

    def test_intermediate_node_hidden_when_no_child_survives(self, db_session):
        user = _user_with_access(db_session, [("schools", "Lecteur Écoles", True, False)])
        result = filter_menu_for_user(_TREE, db_session, user, set())
        ids = {n["id"] for n in result}
        assert "root_courses_group" not in ids  # son seul enfant (courses) n'est pas lisible

    def test_panel_without_resource_key_never_gated(self, db_session):
        # Aucun droit du tout, mais un panel sans resourceKey (TimetableGrid) reste affiché.
        user = _user_with_access(db_session, [("schools", "Sans rapport", True, False)])
        result = filter_menu_for_user(_TREE, db_session, user, set())
        ids = {n["id"] for n in result}
        assert "root_pivot" in ids

    def test_readonly_flag_set_when_no_write_access(self, db_session):
        user = _user_with_access(db_session, [("schools", "Lecture seule Écoles", True, False)])
        result = filter_menu_for_user(_TREE, db_session, user, set())
        node = next(n for n in result if n["id"] == "root_schools")
        assert node["panels"][0]["access"]["readOnly"] is True

    def test_readonly_flag_false_when_write_access_granted(self, db_session):
        user = _user_with_access(db_session, [("schools", "Écriture Écoles", True, True)])
        result = filter_menu_for_user(_TREE, db_session, user, set())
        node = next(n for n in result if n["id"] == "root_schools")
        assert node["panels"][0]["access"]["readOnly"] is False

    def test_action_leaf_requires_write_not_just_read(self, db_session):
        user = _user_with_access(db_session, [("courses", "Lecture seule Cours", True, False)])
        result = filter_menu_for_user(_TREE, db_session, user, set())
        ids = {n["id"] for n in result}
        assert "root_action" not in ids  # lecture seule, pas d'écriture

        user2 = _user_with_access(db_session, [("courses", "Écriture Cours", True, True)])
        result2 = filter_menu_for_user(_TREE, db_session, user2, set())
        ids2 = {n["id"] for n in result2}
        assert "root_action" in ids2

    def test_groups_tag_restricts_branch_even_with_resource_access(self, db_session):
        # Droit de lecture sur schools, mais pas membre du groupe "Admin Test" exigé par la balise.
        user = _user_with_access(db_session, [("schools", "Lecteur Écoles Large", True, False)])
        result = filter_menu_for_user(_TREE, db_session, user, group_names=set())
        ids = {n["id"] for n in result}
        assert "root_gated" not in ids

        result_admin = filter_menu_for_user(_TREE, db_session, user, group_names={"Admin Test"})
        ids_admin = {n["id"] for n in result_admin}
        assert "root_gated" in ids_admin

    def test_empty_access_yields_only_panels_without_resource_key(self, db_session):
        # Sans aucun droit, seuls les panels SANS resourceKey (non gatables par nature, ex:
        # TimetableGrid) survivent — voir test_panel_without_resource_key_never_gated ci-dessus.
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        result = filter_menu_for_user(_TREE, db_session, user, set())
        assert {n["id"] for n in result} == {"root_pivot"}


class TestRealUiJsonWithAdminGroup:
    def test_admin_group_sees_the_entire_real_menu_unfiltered(self, db_session):
        """L'utilisateur du groupe Admin (droits complets, sans domaine) doit voir exactement le
        même arbre que le ui.json brut — le filtrage ne doit rien retirer pour lui."""
        from backend.app.core.init_db import seed_admin_access

        seed_admin_access(db_session)
        admin_group = db_session.query(ResGroup).filter(ResGroup.name == "Admin").first()
        user = User.create(db_session, {"first_name": "Admin", "last_name": "Test", "email": None})
        admin_group.update(db_session, {"user_ids": [user.id]})

        file_path = os.path.join(os.path.dirname(__file__), "..", "app", "api", "ui.json")
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        validate_menu_ids(raw)

        filtered = filter_menu_for_user(raw, db_session, user, group_names={"Admin"})

        def count_leaves(nodes):
            total = 0
            for n in nodes:
                if n.get("children"):
                    total += count_leaves(n["children"])
                else:
                    total += 1
            return total

        assert count_leaves(filtered) == count_leaves(raw)

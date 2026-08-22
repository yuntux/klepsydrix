"""
Tests pour le modèle `CustomFilter` (filtres personnalisés persistés sur une generic list view —
voir models/custom_filter.py). Couvre : anti-spoofing du propriétaire, validation structurelle du
domaine/de la ressource, et la portée de lecture "own OR shared" seedée pour le groupe Consultation
(voir init_db.py::seed_readonly_access, READONLY_CUSTOM_DOMAINS).
"""
import json
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base, AccessDeniedError
from backend.app.models import CustomFilter, User, ResGroup, IrModelAccess, SystemSetting
from backend.tests.db_test_utils import make_test_engine

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


def _make_user_as(db, user_id):
    db.klepsydrix_user_id = user_id


def _make_user_with_full_custom_filter_access(db):
    """Utilisateur membre d'un groupe ad hoc avec perm_create/read/write/unlink=True sans domaine
    sur custom_filters — équivalent d'un groupe "Utilisateur standard" que l'administrateur d'une
    base réelle configurerait explicitement (voir READONLY_CUSTOM_DOMAINS, init_db.py : Consultation
    reste volontairement sans perm_create)."""
    user = User.create(db, {"first_name": "A", "last_name": "A", "email": None})
    group = ResGroup.create(db, {"name": "Utilisateur standard"})
    group.update(db, {"user_ids": [user.id]})
    IrModelAccess.create(db, {
        "model": "custom_filters", "group_id": group.id,
        "perm_read": True, "perm_write": True, "perm_create": True, "perm_unlink": True,
    })
    return user


class TestOwnership:
    def test_create_forces_current_user_as_owner(self, db_session):
        owner = _make_user_with_full_custom_filter_access(db_session)
        other = User.create(db_session, {"first_name": "B", "last_name": "B", "email": None})
        _make_user_as(db_session, owner.id)

        f = CustomFilter.create(db_session, {
            "name": "Mes classes", "resource": "divisions", "user_id": other.id,
        })
        assert f.user_id == owner.id

    def test_update_cannot_reassign_owner(self, db_session):
        owner = _make_user_with_full_custom_filter_access(db_session)
        other = User.create(db_session, {"first_name": "B", "last_name": "B", "email": None})
        _make_user_as(db_session, owner.id)
        f = CustomFilter.create(db_session, {"name": "Mes classes", "resource": "divisions"})

        f.update(db_session, {"user_id": other.id, "name": "Renommé"})
        assert f.user_id == owner.id
        assert f.name == "Renommé"

    def test_system_mode_requires_explicit_user_id(self, db_session):
        owner = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        # db.klepsydrix_user_id jamais posé (mode système, ex: seed/import) : rien ne force le
        # propriétaire, l'appelant doit le fournir explicitement.
        f = CustomFilter.create(db_session, {"name": "Import", "resource": "divisions", "user_id": owner.id})
        assert f.user_id == owner.id


class TestStructuralValidation:
    def test_rejects_unknown_resource(self, db_session):
        owner = _make_user_with_full_custom_filter_access(db_session)
        _make_user_as(db_session, owner.id)
        with pytest.raises(ValueError):
            CustomFilter.create(db_session, {"name": "X", "resource": "not_a_real_table"})

    def test_rejects_malformed_domain(self, db_session):
        owner = _make_user_with_full_custom_filter_access(db_session)
        _make_user_as(db_session, owner.id)
        with pytest.raises(ValueError):
            CustomFilter.create(db_session, {
                "name": "X", "resource": "divisions", "domain": json.dumps([("not_a_real_field", "=", "x")]),
            })

    def test_accepts_valid_domain_on_a_direct_field(self, db_session):
        owner = _make_user_with_full_custom_filter_access(db_session)
        _make_user_as(db_session, owner.id)
        f = CustomFilter.create(db_session, {
            "name": "Exclues STS", "resource": "divisions",
            "domain": json.dumps([["is_excluded_from_sts", "=", True]]),
        })
        assert json.loads(f.domain) == [["is_excluded_from_sts", "=", True]]


class TestConsultationReadScope:
    def test_consultation_member_sees_only_own_and_shared_filters(self, db_session):
        from backend.app.core.init_db import seed_readonly_access
        seed_readonly_access(db_session)

        owner = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        other = User.create(db_session, {"first_name": "B", "last_name": "B", "email": None})
        consultation = db_session.query(ResGroup).filter(ResGroup.name == "Consultation").first()
        consultation.update(db_session, {"user_ids": [owner.id, other.id]})

        # Données créées en mode système (db.klepsydrix_user_id non posé) : Consultation n'a pas
        # perm_create (voir test ci-dessous), hors du périmètre de CE test qui ne porte que sur la
        # portée de LECTURE.
        CustomFilter.create(db_session, {"name": "Privé de B", "resource": "divisions", "is_shared": False, "user_id": other.id})
        CustomFilter.create(db_session, {"name": "Partagé de B", "resource": "divisions", "is_shared": True, "user_id": other.id})
        CustomFilter.create(db_session, {"name": "Privé de A", "resource": "divisions", "is_shared": False, "user_id": owner.id})

        _make_user_as(db_session, owner.id)
        visible_names = {f.name for f in CustomFilter.read(db_session)}
        assert visible_names == {"Privé de A", "Partagé de B"}

    def test_consultation_member_cannot_write_or_create_without_a_dedicated_group(self, db_session):
        """Consultation reste un groupe strictement en lecture seule (voir init_db.py) : la
        création/gestion de filtres personnels par un profil non-Admin nécessite un groupe dédié
        configuré par l'administrateur, comme pour n'importe quel autre modèle."""
        from backend.app.core.init_db import seed_readonly_access
        seed_readonly_access(db_session)

        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        consultation = db_session.query(ResGroup).filter(ResGroup.name == "Consultation").first()
        consultation.update(db_session, {"user_ids": [user.id]})

        _make_user_as(db_session, user.id)
        with pytest.raises(AccessDeniedError):
            CustomFilter.create(db_session, {"name": "X", "resource": "divisions"})

    def test_admin_can_manage_any_users_filter(self, db_session):
        from backend.app.core.init_db import seed_admin_access
        seed_admin_access(db_session)

        owner = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        admin = User.create(db_session, {"first_name": "Ad", "last_name": "Min", "email": None})
        admin_group = db_session.query(ResGroup).filter(ResGroup.name == "Admin").first()
        admin_group.update(db_session, {"user_ids": [admin.id]})

        # Créé en mode système : seul le contrôle d'écriture/suppression par l'Admin est testé ici.
        f = CustomFilter.create(db_session, {"name": "Privé de A", "resource": "divisions", "user_id": owner.id})

        _make_user_as(db_session, admin.id)
        f.update(db_session, {"name": "Renommé par Admin"})
        assert f.name == "Renommé par Admin"
        f.delete(db_session)

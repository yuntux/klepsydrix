"""
Champs d'audit communs à tous les modèles (voir models/base.py : `create_user_id`, `write_user_id`,
`create_date`, `write_date`, façon Odoo).

Ce qui est vérifié ici : ils sont posés par le SERVEUR à chaque écriture, quel que soit le chemin
emprunté, et l'API ne permet jamais de les fixer — sans quoi ce ne serait pas une trace, seulement
un champ de plus.
"""
import time

import pytest
from sqlalchemy.orm import sessionmaker

from backend.app.api.generic import make_pydantic_model
from backend.app.models.base import AUDIT_COLUMNS, Base
from backend.app.models import User
from backend.app.models.discipline import Discipline
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _make_admin(db, first_name, last_name, email):
    """Un utilisateur réellement autorisé à écrire : poser `klepsydrix_user_id` active le moteur de
    droits (voir base.py::_check_class_access), un compte sans groupe se verrait tout refuser."""
    from backend.app.core.init_db import seed_admin_access
    from backend.app.models.access import ResGroup

    user = User.create(db, {"first_name": first_name, "last_name": last_name, "email": email})
    admin_group = db.query(ResGroup).filter(ResGroup.name == "Admin").first()
    if admin_group is None:
        seed_admin_access(db)
        admin_group = db.query(ResGroup).filter(ResGroup.name == "Admin").first()
    admin_group.update(db, {"user_ids": list({u.id for u in admin_group.users} | {user.id})})
    db.commit()
    return user


@pytest.fixture
def author(db_session):
    """Un utilisateur courant, comme en pose `database.py::current_db_user` à la frontière HTTP."""
    user = _make_admin(db_session, "Ada", "Lovelace", "ada@example.fr")
    db_session.klepsydrix_user_id = user.id
    return user


class TestStampingOnCreate:
    def test_all_four_fields_are_set(self, db_session, author):
        discipline = Discipline.create(db_session, {"code": "L0100", "name": "Lettres"})
        db_session.commit()

        assert discipline.create_user_id == author.id
        assert discipline.write_user_id == author.id
        assert discipline.create_date is not None
        # À la création, les deux horodatages sont le même instant — c'est ce qui permet de
        # reconnaître un enregistrement jamais modifié depuis.
        assert discipline.create_date == discipline.write_date

    def test_a_system_write_leaves_the_user_columns_null(self, db_session):
        """Seed, import, tâche de fond, solveur : personne à désigner. Les dates restent posées —
        « écrit par le système » se distingue ainsi de « écrit par quelqu'un »."""
        discipline = Discipline.create(db_session, {"code": "M0100", "name": "Maths"})
        db_session.commit()

        assert discipline.create_user_id is None
        assert discipline.write_user_id is None
        assert discipline.create_date is not None


class TestStampingOnUpdate:
    def test_write_fields_advance_and_creation_fields_do_not(self, db_session, author):
        discipline = Discipline.create(db_session, {"code": "L0100", "name": "Lettres"})
        db_session.commit()
        created_at, created_by = discipline.create_date, discipline.create_user_id

        db_session.klepsydrix_user_id = None  # création du second compte en mode système
        other = _make_admin(db_session, "Grace", "Hopper", "grace@example.fr")
        db_session.klepsydrix_user_id = other.id
        time.sleep(0.01)  # horloge à la microseconde : il faut un écart mesurable

        discipline.update(db_session, {"name": "Lettres modernes"})
        db_session.commit()

        assert discipline.write_user_id == other.id
        assert discipline.write_date > created_at
        assert discipline.create_user_id == created_by  # la création ne se réécrit jamais
        assert discipline.create_date == created_at

    def test_a_plain_read_changes_nothing(self, db_session, author):
        discipline = Discipline.create(db_session, {"code": "L0100", "name": "Lettres"})
        db_session.commit()
        before = discipline.write_date

        Discipline.read(db_session, domain={"id": discipline.id})
        db_session.commit()

        assert discipline.write_date == before


class TestApiSurface:
    """Les champs d'audit se lisent, ne s'écrivent pas — comme `id`."""

    def test_absent_from_the_creation_and_update_schemas(self):
        create_schema = make_pydantic_model(Discipline, all_optional=False)
        update_schema = make_pydantic_model(Discipline, all_optional=True)

        for column in AUDIT_COLUMNS:
            assert column not in create_schema.model_fields
            assert column not in update_schema.model_fields

    def test_present_in_the_read_schema(self):
        """Une vue qui les nomme explicitement doit pouvoir les afficher (voir
        App.vue::TECHNICAL_FIELD_KEYS) — ils font donc partie du schéma de lecture."""
        read_schema = make_pydantic_model(Discipline, include_id=True)

        for column in AUDIT_COLUMNS:
            assert column in read_schema.model_fields
        assert "id" in read_schema.model_fields

    def test_a_client_supplied_value_is_ignored(self, db_session, author):
        """Défense en profondeur : même en contournant le schéma, la valeur posée par le serveur
        l'emporte — `stamp_audit_fields` s'exécute à chaque flush, après l'appelant."""
        discipline = Discipline.create(db_session, {
            "code": "L0100", "name": "Lettres", "create_user_id": 999999,
        })
        db_session.commit()

        assert discipline.create_user_id == author.id


class TestEveryModelCarriesThem:
    def test_columns_exist_on_an_arbitrary_sample_of_tables(self):
        """Déclarés une seule fois sur `Base` (declared_attr), donc présents partout — un modèle
        ajouté demain les aura sans que personne y pense."""
        for model in (User, Discipline):
            for column in AUDIT_COLUMNS:
                assert column in model.__table__.columns

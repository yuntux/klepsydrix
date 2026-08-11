"""
Tests pour le modèle Teacher et son entourage : tables de référence RH (ref_*), objets de
liaison à volume horaire (teacher_*), suppression protégée générique (RESTRICT), contrainte
d'unicité nom/prénom/date de naissance. Fichier destiné à accueillir tout futur test lié à
Teacher — ne pas créer un nouveau fichier test_teacher_*.py pour un prochain besoin.
"""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Teacher, RefAra, RefCity, RefCountry, TeacherAra, TeacherDiscipline,
    Discipline, SystemSetting,
)

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DATABASE_URL, echo=False)
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


def _make_teacher(db, code="T1", **overrides):
    school = db.query(School).first()
    if not school:
        school = School.create(db, {"uai": "1234567A", "name": "Collège Test"})
    vals = {"code": code, "last_name": "Dupont", "first_name": "Marc", "school_id": school.id}
    vals.update(overrides)
    return Teacher.create(db, vals)


class TestRefDeleteRestrict:
    def test_cannot_delete_ref_ara_referenced_by_a_teacher(self, db_session):
        teacher = _make_teacher(db_session)
        ref_ara = RefAra.create(db_session, {"name": "ARA Test"})
        TeacherAra.create(db_session, {"teacher_id": teacher.id, "ref_ara_id": ref_ara.id, "duration_minutes": 60})

        with pytest.raises(ValueError, match="Impossible de supprimer"):
            ref_ara.delete(db_session)

    def test_ref_ara_deletable_once_unreferenced(self, db_session):
        teacher = _make_teacher(db_session)
        ref_ara = RefAra.create(db_session, {"name": "ARA Test"})
        line = TeacherAra.create(db_session, {"teacher_id": teacher.id, "ref_ara_id": ref_ara.id, "duration_minutes": 60})
        line.delete(db_session)

        ref_ara.delete(db_session)
        assert db_session.query(RefAra).filter(RefAra.id == ref_ara.id).first() is None

    def test_cannot_delete_discipline_referenced_by_teacher_discipline(self, db_session):
        teacher = _make_teacher(db_session)
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        TeacherDiscipline.create(db_session, {"teacher_id": teacher.id, "discipline_id": discipline.id, "duration_minutes": 30})

        with pytest.raises(ValueError, match="Impossible de supprimer"):
            discipline.delete(db_session)


class TestTeacherCascadeDelete:
    def test_deleting_teacher_cascades_to_its_lines(self, db_session):
        teacher = _make_teacher(db_session)
        ref_ara = RefAra.create(db_session, {"name": "ARA Test"})
        line = TeacherAra.create(db_session, {"teacher_id": teacher.id, "ref_ara_id": ref_ara.id, "duration_minutes": 60})

        teacher.delete(db_session)

        assert db_session.query(TeacherAra).filter(TeacherAra.id == line.id).first() is None
        # Le ref_ara lui-même n'a aucune raison de disparaître (RESTRICT côté ref, pas CASCADE)
        assert db_session.query(RefAra).filter(RefAra.id == ref_ara.id).first() is not None


class TestTeacherIdentityUnique:
    def test_cannot_create_two_teachers_with_same_identity(self, db_session):
        _make_teacher(db_session, code="T1", last_name="Dupont", first_name="Marc", birth_date=date(1980, 1, 1))
        with pytest.raises(ValueError, match="existe déjà"):
            _make_teacher(db_session, code="T2", last_name="Dupont", first_name="Marc", birth_date=date(1980, 1, 1))

    def test_same_name_without_birth_date_is_allowed(self, db_session):
        _make_teacher(db_session, code="T1", last_name="Dupont", first_name="Marc")
        # Aucune birth_date sur les deux : la contrainte ne s'applique pas (voir _check_identity_unique)
        _make_teacher(db_session, code="T2", last_name="Dupont", first_name="Marc")

    def test_same_name_different_birth_date_is_allowed(self, db_session):
        _make_teacher(db_session, code="T1", last_name="Dupont", first_name="Marc", birth_date=date(1980, 1, 1))
        _make_teacher(db_session, code="T2", last_name="Dupont", first_name="Marc", birth_date=date(1985, 5, 5))


class TestRefCityUnique:
    def test_cannot_create_two_cities_with_same_name_and_zip_code(self, db_session):
        RefCity.create(db_session, {"name": "Paris", "zip_code": "75001"})
        with pytest.raises(ValueError, match="existe déjà"):
            RefCity.create(db_session, {"name": "Paris", "zip_code": "75001"})

    def test_same_name_different_zip_code_is_allowed(self, db_session):
        RefCity.create(db_session, {"name": "Paris", "zip_code": "75001"})
        RefCity.create(db_session, {"name": "Paris", "zip_code": "75002"})


class TestTeacherOnchangeAddressCity:
    def test_selecting_a_city_prefills_country(self, db_session):
        # @onchange reçoit désormais une vraie session BDD (voir base.py::process_onchange,
        # architecture.md §15.R) — peut donc résoudre address_city_id -> RefCity.country_id.
        country = RefCountry.create(db_session, {"name": "France"})
        city = RefCity.create(db_session, {"name": "Paris", "country_id": country.id, "zip_code": "75001"})

        result = Teacher.process_onchange(db_session, {"address_city_id": city.id}, "address_city_id")

        assert result.get("address_country_id") == country.id

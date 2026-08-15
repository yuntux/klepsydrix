"""
Tests pour User/UserIdentityProvider/Parent et le mixin HasUserAccount (Teacher, NonTeachingStaff,
Student, Parent) — voir architecture.md, "Architecture Multi-Base et Routage HTTP" / specs/. Fichier
destiné à accueillir tout futur test lié à l'authentification/aux comptes utilisateur.
"""
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Teacher, NonTeachingStaff, Student, Parent, User, UserIdentityProvider,
    Division, Mef, MefDivision, RefGrade, SystemSetting, Course, Subject, Discipline,
)
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


def _make_school(db):
    return School.create(db, {"uai": "1234567A", "name": "Collège Test"})


def _make_student(db, **overrides):
    school = _make_school(db)
    division = Division.create(db, {"code": "6A", "name": "6ème A", "school_id": school.id})
    ref_grade = RefGrade.create(db, {"name": "6EME"})
    mef = Mef.create(db, {
        "school_id": school.id, "code_national": "MEF_TEST", "name": "MEF", "ref_grade_id": ref_grade.id,
        "max_students_per_class": 30, "forecast_student_count": 30,
    })
    MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 30})
    vals = {"first_name": "Léa", "last_name": "Martin", "division_id": division.id, "mef_id": mef.id}
    vals.update(overrides)
    return Student.create(db, vals)


class TestHasUserAccountSync:
    def test_update_syncs_mirror_fields_to_user(self, db_session):
        user = User.create(db_session, {"first_name": "Marc", "last_name": "Dupont", "email": "old@example.com"})
        teacher = Teacher.create(db_session, {
            "code": "T1", "first_name": "Marc", "last_name": "Dupont",
            "school_id": _make_school(db_session).id, "user_id": user.id,
        })
        teacher.update(db_session, {"email": "marc.dupont@example.com"})
        db_session.refresh(user)
        assert user.email == "marc.dupont@example.com"
        assert user.first_name == "Marc"

    def test_sync_does_not_propagate_null_source_field(self, db_session):
        # Teacher.first_name est nullable, contrairement à User.first_name — une valeur absente
        # côté Teacher ne doit jamais écraser le prénom déjà connu côté User.
        user = User.create(db_session, {"first_name": "Marc", "last_name": "Dupont", "email": None})
        teacher = Teacher.create(db_session, {
            "code": "T2", "first_name": None, "last_name": "Dupont",
            "school_id": _make_school(db_session).id, "user_id": user.id,
        })
        teacher.update(db_session, {"last_name": "Durand"})
        db_session.refresh(user)
        assert user.first_name == "Marc"
        assert user.last_name == "Durand"

    def test_student_sync_ignores_email_field_it_does_not_have(self, db_session):
        # Student ne porte pas de colonne email — _user_mirror_fields() doit s'y adapter sans lever.
        user = User.create(db_session, {"first_name": "Léa", "last_name": "Martin", "email": "contact@example.com"})
        student = _make_student(db_session, user_id=user.id)
        student.update(db_session, {"last_name": "Bernard"})
        db_session.refresh(user)
        assert user.last_name == "Bernard"
        assert user.email == "contact@example.com"  # jamais touché, Student n'a pas ce champ

    def test_deleting_person_deletes_linked_user(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        nts = NonTeachingStaff.create(db_session, {
            "first_name": "Jean", "last_name": "Petit", "role": "AESH",
            "school_id": _make_school(db_session).id, "user_id": user.id,
        })
        nts.delete(db_session)
        assert db_session.get(User, user.id) is None

    def test_cannot_delete_user_directly_while_referenced(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        NonTeachingStaff.create(db_session, {
            "first_name": "Jean", "last_name": "Petit", "role": "AESH",
            "school_id": _make_school(db_session).id, "user_id": user.id,
        })
        with pytest.raises(ValueError, match="Impossible de supprimer"):
            user.delete(db_session)

    def test_user_cannot_be_linked_to_two_person_records(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        school = _make_school(db_session)
        NonTeachingStaff.create(db_session, {
            "first_name": "Jean", "last_name": "Petit", "role": "AESH", "school_id": school.id, "user_id": user.id,
        })
        with pytest.raises(ValueError, match="déjà rattaché"):
            Teacher.create(db_session, {
                "code": "T3", "first_name": "Jean", "last_name": "Petit", "school_id": school.id, "user_id": user.id,
            })


class TestParentAndStudentLinks:
    def test_student_can_reference_two_parents(self, db_session):
        parent1 = Parent.create(db_session, {"first_name": "Alice", "last_name": "Martin", "phone": "0600000001"})
        parent2 = Parent.create(db_session, {"first_name": "Bob", "last_name": "Martin", "phone": "0600000002"})
        student = _make_student(db_session, parent1_id=parent1.id, parent2_id=parent2.id)
        assert student.parent1.first_name == "Alice"
        assert student.parent2.first_name == "Bob"

    def test_deleting_parent_sets_student_parent_field_to_null(self, db_session):
        parent1 = Parent.create(db_session, {"first_name": "Alice", "last_name": "Martin"})
        student = _make_student(db_session, parent1_id=parent1.id)
        parent1.delete(db_session)
        db_session.refresh(student)
        assert student.parent1_id is None


class TestUserIdentityProviderPrivateField:
    def test_password_hash_never_serialized(self, db_session):
        from backend.app.api.generic import sqla_to_dict

        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.create(db_session, {
            "user_id": user.id, "provider_key": "local", "external_subject": "jean.petit",
            "password_hash": "argon2id$super-secret-hash",
        })
        serialized = sqla_to_dict(idp)
        assert "password_hash" not in serialized
        # La colonne existe bien en base (l'exclusion est côté API générique, pas au niveau du modèle).
        assert idp.password_hash == "argon2id$super-secret-hash"

    def test_password_hash_field_absent_from_generated_schemas(self, db_session):
        from backend.app.api.generic import make_pydantic_model

        create_schema = make_pydantic_model(UserIdentityProvider, all_optional=False)
        assert "password_hash" not in create_schema.model_fields

    def test_local_password_register_and_verify(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": "jean@example.com"})
        UserIdentityProvider.register_local_password(db_session, user.id, "jean@example.com", "correct horse battery staple")

        ok = UserIdentityProvider.verify_local_password(db_session, "jean@example.com", "correct horse battery staple")
        assert ok is not None
        assert ok.user_id == user.id

        wrong = UserIdentityProvider.verify_local_password(db_session, "jean@example.com", "wrong password")
        assert wrong is None

        unknown = UserIdentityProvider.verify_local_password(db_session, "nobody@example.com", "whatever")
        assert unknown is None

    def test_local_password_hash_is_argon2id_never_plaintext(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.register_local_password(db_session, user.id, "jean", "s3cret!")
        assert idp.password_hash != "s3cret!"
        assert idp.password_hash.startswith("$argon2id$")

    def test_set_local_password_changes_hash(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.register_local_password(db_session, user.id, "jean", "old-password")
        idp.set_local_password(db_session, "new-password")

        assert UserIdentityProvider.verify_local_password(db_session, "jean", "old-password") is None
        assert UserIdentityProvider.verify_local_password(db_session, "jean", "new-password") is not None

    def test_unique_provider_subject_pair(self, db_session):
        user1 = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        user2 = User.create(db_session, {"first_name": "B", "last_name": "B", "email": None})
        UserIdentityProvider.create(db_session, {"user_id": user1.id, "provider_key": "educonnect", "external_subject": "sub-1"})
        with pytest.raises(Exception):
            UserIdentityProvider.create(db_session, {"user_id": user2.id, "provider_key": "educonnect", "external_subject": "sub-1"})


class TestCourseStudentIds:
    def test_student_ids_aggregates_via_division_and_class_parts(self, db_session):
        student_via_division = _make_student(db_session, first_name="Léa")
        subject = Subject.create(db_session, {
            "code": "MATH", "code_nomenclature": "MATH1", "short_name": "Maths", "name": "Mathématiques",
            "discipline_id": Discipline.create(db_session, {"code": "SCI", "name": "Sciences"}).id,
        })
        course = Course.create(db_session, {
            "subject_id": subject.id, "school_id": student_via_division.division.school_id,
            "division_ids": [student_via_division.division_id],
        })
        db_session.commit()
        assert course.student_ids == [student_via_division.id]

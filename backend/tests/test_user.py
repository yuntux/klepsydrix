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
    StudentParentLink,
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
    def test_student_can_reference_several_parents(self, db_session):
        parent1 = Parent.create(db_session, {"first_name": "Alice", "last_name": "Martin", "mobile_phone": "0600000001"})
        parent2 = Parent.create(db_session, {"first_name": "Bob", "last_name": "Martin", "mobile_phone": "0600000002"})
        student = _make_student(db_session)
        StudentParentLink.create(db_session, {"student_id": student.id, "parent_id": parent1.id})
        StudentParentLink.create(db_session, {"student_id": student.id, "parent_id": parent2.id})
        db_session.refresh(student)
        assert {link.parent.first_name for link in student.parent_links} == {"Alice", "Bob"}

    def test_deleting_parent_removes_the_link(self, db_session):
        parent1 = Parent.create(db_session, {"first_name": "Alice", "last_name": "Martin"})
        student = _make_student(db_session)
        StudentParentLink.create(db_session, {"student_id": student.id, "parent_id": parent1.id})
        parent1.delete(db_session)
        db_session.refresh(student)
        assert student.parent_links == []


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
        # "CorrectHorse8!" plutôt que le "correct horse battery staple" classique : conforme à la
        # politique de robustesse désormais appliquée (TestPasswordStrength ci-dessous) — longueur
        # ET diversité de caractères, pas la longueur seule.
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": "jean@example.com"})
        UserIdentityProvider.register_local_password(db_session, user.id, "jean@example.com", "CorrectHorse8!")

        ok = UserIdentityProvider.verify_local_password(db_session, "jean@example.com", "CorrectHorse8!")
        assert ok is not None
        assert ok.user_id == user.id

        wrong = UserIdentityProvider.verify_local_password(db_session, "jean@example.com", "wrong password")
        assert wrong is None

        unknown = UserIdentityProvider.verify_local_password(db_session, "nobody@example.com", "whatever")
        assert unknown is None

    def test_local_password_hash_is_argon2id_never_plaintext(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.register_local_password(db_session, user.id, "jean", "S3cret!!")
        assert idp.password_hash != "S3cret!!"
        assert idp.password_hash.startswith("$argon2id$")

    def test_set_local_password_changes_hash(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.register_local_password(db_session, user.id, "jean", "OldPass8!")
        idp.set_local_password(db_session, "NewPass9?")

        assert UserIdentityProvider.verify_local_password(db_session, "jean", "OldPass8!") is None
        assert UserIdentityProvider.verify_local_password(db_session, "jean", "NewPass9?") is not None

    def test_unique_provider_subject_pair(self, db_session):
        user1 = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        user2 = User.create(db_session, {"first_name": "B", "last_name": "B", "email": None})
        UserIdentityProvider.create(db_session, {"user_id": user1.id, "provider_key": "educonnect", "external_subject": "sub-1"})
        with pytest.raises(Exception):
            UserIdentityProvider.create(db_session, {"user_id": user2.id, "provider_key": "educonnect", "external_subject": "sub-1"})


class TestUserActive:
    def test_active_defaults_true(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        assert user.active is True

    def test_active_can_be_toggled(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        user.update(db_session, {"active": False})
        db_session.refresh(user)
        assert user.active is False


class TestEmailNotClearable:
    def test_cannot_clear_an_existing_email(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": "jean@example.com"})
        with pytest.raises(ValueError, match="Impossible de supprimer l'adresse email"):
            user.update(db_session, {"email": None})

    def test_cannot_clear_an_existing_email_with_empty_string(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": "jean@example.com"})
        with pytest.raises(ValueError, match="Impossible de supprimer l'adresse email"):
            user.update(db_session, {"email": ""})

    def test_can_replace_an_existing_email_with_another(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": "jean@example.com"})
        user.update(db_session, {"email": "jean.petit@example.com"})
        db_session.refresh(user)
        assert user.email == "jean.petit@example.com"

    def test_can_set_an_email_when_none_was_set(self, db_session):
        # HasUserAccount._sync_user_account (ex: synchro Teacher/Student -> User) ne propage jamais
        # None, mais un email jamais renseigné à la création doit tout de même pouvoir être posé
        # plus tard sans que ce garde-fou (pensé pour un RETRAIT) ne s'y oppose.
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        user.update(db_session, {"email": "jean@example.com"})
        db_session.refresh(user)
        assert user.email == "jean@example.com"


class TestPasswordStrength:
    def test_rejects_password_shorter_than_minimum(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        with pytest.raises(ValueError, match="au moins 8 caractères"):
            UserIdentityProvider.register_local_password(db_session, user.id, "jean", "Ab1!")

    def test_rejects_password_without_enough_character_diversity(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        # 8+ caractères, une seule classe (minuscules) : longueur suffisante, diversité insuffisante.
        with pytest.raises(ValueError, match="3 des 4 catégories"):
            UserIdentityProvider.register_local_password(db_session, user.id, "jean", "abcdefghijk")

    def test_accepts_password_meeting_both_requirements(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.register_local_password(db_session, user.id, "jean", "Correct8!")
        assert idp.password_hash is not None

    def test_set_local_password_also_enforces_strength(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.register_local_password(db_session, user.id, "jean", "Correct8!")
        with pytest.raises(ValueError, match="au moins 8 caractères"):
            idp.set_local_password(db_session, "weak")


class TestMustChangePassword:
    def test_defaults_false(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.register_local_password(db_session, user.id, "jean", "Correct8!")
        assert idp.must_change_password is False

    def test_set_local_password_clears_the_flag(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.register_local_password(db_session, user.id, "jean", "Correct8!")
        idp.update(db_session, {"must_change_password": True})
        idp.set_local_password(db_session, "AnotherGood9?")
        db_session.refresh(idp)
        assert idp.must_change_password is False


class TestVerifyPassword:
    def test_verify_password_matches_verify_local_password(self, db_session):
        """verify_password (instance) et verify_local_password (classmethod) partagent désormais la
        même logique — voir models/user.py::UserIdentityProvider.verify_password."""
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.register_local_password(db_session, user.id, "jean", "Correct8!")
        assert idp.verify_password(db_session, "Correct8!") is True
        assert idp.verify_password(db_session, "wrong") is False

    def test_verify_password_false_when_no_hash_set(self, db_session):
        user = User.create(db_session, {"first_name": "Jean", "last_name": "Petit", "email": None})
        idp = UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "educonnect", "external_subject": "sub-1"})
        assert idp.verify_password(db_session, "anything") is False


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

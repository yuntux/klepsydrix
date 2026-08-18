"""
Tests pour le moteur de droits façon Odoo (ResGroup/IrModelAccess, core/access_control.py) — voir
architecture.md, plan "Multi-SGBD, Multi-Base, Utilisateurs/IDP, Droits, Console Admin". Fichier
destiné à accueillir tout futur test lié aux droits/habilitations.
"""
import json
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base, AccessDeniedError
from backend.app.models import (
    School, Discipline, Subject, Division, Mef, MefDivision, RefGrade, Student, Course,
    User, ResGroup, IrModelAccess, SystemSetting,
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


def _make_user_as(db, user_id):
    """Simule la frontière HTTP (voir database.py::current_db_user) pour le reste du test."""
    db.klepsydrix_user_id = user_id


def _make_student_with_course(db):
    """École + division + MEF + élève + un Course rattaché à sa division."""
    school = School.create(db, {"uai": "1234567A", "name": "Collège Test"})
    division = Division.create(db, {"code": "6A", "name": "6ème A", "school_id": school.id})
    ref_grade = RefGrade.create(db, {"name": "6EME"})
    mef = Mef.create(db, {
        "school_id": school.id, "code_national": "MEF_TEST", "name": "MEF", "ref_grade_id": ref_grade.id,
        "max_students_per_class": 30, "forecast_student_count": 30,
    })
    MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 30})
    student = Student.create(db, {"first_name": "Léa", "last_name": "Martin", "division_id": division.id, "mef_id": mef.id})
    disc = Discipline.create(db, {"code": "SCI", "name": "Sciences"})
    subject = Subject.create(db, {"code": "MATH", "code_nomenclature": "MATH1", "short_name": "Maths", "name": "Mathématiques", "discipline_id": disc.id})
    course = Course.create(db, {"subject_id": subject.id, "school_id": school.id, "division_ids": [division.id]})
    other_division = Division.create(db, {"code": "5A", "name": "5ème A", "school_id": school.id})
    other_course = Course.create(db, {"subject_id": subject.id, "school_id": school.id, "division_ids": [other_division.id]})
    return student, course, other_course


class TestRpcGuard:
    """
    School.test_class_method (non décorée) / test_instance_method (@requires_access("write")) —
    voir school.py, déjà réservées à l'exercice du mécanisme RPC générique (test_generic.py),
    décorées/non décorées spécifiquement pour couvrir les deux branches du garde-fou ici.
    """
    def test_undecorated_method_refused_when_user_set(self, db_session):
        from fastapi import HTTPException
        from backend.app.api.generic import make_class_call_endpoint, CallPayload

        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Tout"})
        group.update(db_session, {"user_ids": [user.id]})
        IrModelAccess.create(db_session, {"model": "schools", "group_id": group.id, "perm_read": True, "perm_write": True})
        _make_user_as(db_session, user.id)

        endpoint = make_class_call_endpoint(School)
        with pytest.raises(HTTPException) as exc_info:
            endpoint("test_class_method", CallPayload(args=[5], kwargs={}), db_session)
        assert exc_info.value.status_code == 403

    def test_decorated_method_allowed_with_matching_access(self, db_session):
        from backend.app.api.generic import make_instance_call_endpoint, CallPayload

        school = School.create(db_session, {"uai": "1234567A", "name": "Test"})  # mode système
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Lecteur-Écriveur Écoles"})
        group.update(db_session, {"user_ids": [user.id]})
        IrModelAccess.create(db_session, {"model": "schools", "group_id": group.id, "perm_read": True, "perm_write": True})
        _make_user_as(db_session, user.id)

        endpoint = make_instance_call_endpoint(School)
        result = endpoint(school.id, "test_instance_method", CallPayload(args=[], kwargs={"prefix": "Établissement :"}), db_session)
        assert result == "Établissement : Test"

    def test_decorated_method_refused_without_matching_access(self, db_session):
        """Lecture seule accordée (l'instance est visible) mais pas écriture (exigée par la méthode) : 403, pas 404."""
        from fastapi import HTTPException
        from backend.app.api.generic import make_instance_call_endpoint, CallPayload

        school = School.create(db_session, {"uai": "1234567A", "name": "Test"})  # mode système
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Lecteur seul Écoles"})
        group.update(db_session, {"user_ids": [user.id]})
        IrModelAccess.create(db_session, {"model": "schools", "group_id": group.id, "perm_read": True, "perm_write": False})
        _make_user_as(db_session, user.id)

        endpoint = make_instance_call_endpoint(School)
        with pytest.raises(HTTPException) as exc_info:
            endpoint(school.id, "test_instance_method", CallPayload(args=[], kwargs={"prefix": "x"}), db_session)
        assert exc_info.value.status_code == 403


class TestTimetableEndpointsGuard:
    """
    backend/app/api/endpoints.py (/api/timetable/*) ne passe pas par le CRUD générique — voir
    architecture.md, "audit des contournements". _require_course_access() y a été ajouté
    explicitement ; ce test vérifie qu'il bloque bien plutôt que de se fier à la seule lecture du code.
    """
    def test_score_endpoint_requires_read_access(self, db_session):
        from fastapi import HTTPException
        from backend.app.api.endpoints import get_score

        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Sans droit Cours"})
        group.update(db_session, {"user_ids": [user.id]})
        _make_user_as(db_session, user.id)

        with pytest.raises(HTTPException) as exc_info:
            get_score(school_id=None, db=db_session)
        assert exc_info.value.status_code == 403

    def test_reset_endpoint_requires_write_access(self, db_session):
        from fastapi import HTTPException
        from backend.app.api.endpoints import reset

        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Lecture seule Cours"})
        group.update(db_session, {"user_ids": [user.id]})
        IrModelAccess.create(db_session, {"model": "courses", "group_id": group.id, "perm_read": True, "perm_write": False})
        _make_user_as(db_session, user.id)

        with pytest.raises(HTTPException) as exc_info:
            reset(db=db_session)
        assert exc_info.value.status_code == 403

    def test_reset_endpoint_allowed_with_write_access(self, db_session):
        from backend.app.api.endpoints import reset

        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Écriture Cours"})
        group.update(db_session, {"user_ids": [user.id]})
        IrModelAccess.create(db_session, {"model": "courses", "group_id": group.id, "perm_read": True, "perm_write": True})
        _make_user_as(db_session, user.id)

        result = reset(db=db_session)
        assert result == {"status": "success"}

    def test_write_endpoint_refused_when_write_right_carries_a_domain(self, db_session):
        """
        Cœur du traitement dissymétrique (voir endpoints.py::_require_course_access) : `perm_write`
        assorti d'un domaine signifie « vous pouvez écrire sur CE sous-ensemble ». Or /reset écrit
        sur TOUS les cours et ne sait pas se restreindre — le laisser passer ferait déborder
        l'écriture hors du domaine, exactement ce que le domaine interdit.
        """
        from fastapi import HTTPException
        from backend.app.api.endpoints import reset

        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Écriture Cours restreinte"})
        group.update(db_session, {"user_ids": [user.id]})
        IrModelAccess.create(db_session, {
            "model": "courses", "group_id": group.id, "perm_read": True, "perm_write": True,
            "domain": json.dumps([("divisions.students.user_id", "=", "user.id")]),
        })
        _make_user_as(db_session, user.id)

        with pytest.raises(HTTPException) as exc_info:
            reset(db=db_session)
        assert exc_info.value.status_code == 403
        assert "ensemble des cours" in exc_info.value.detail

    def test_read_endpoint_still_allowed_when_read_right_carries_a_domain(self, db_session):
        """
        Contrepartie explicite du test précédent : en LECTURE, un domaine ne bloque pas. score et
        heatmap renvoient des agrégats calculés sur tous les cours — limite assumée et documentée
        (architecture.md §18.F), vérifiée ici pour qu'elle ne change pas par accident.
        """
        from backend.app.api.endpoints import get_score

        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Lecture Cours restreinte"})
        group.update(db_session, {"user_ids": [user.id]})
        IrModelAccess.create(db_session, {
            "model": "courses", "group_id": group.id, "perm_read": True,
            "domain": json.dumps([("divisions.students.user_id", "=", "user.id")]),
        })
        _make_user_as(db_session, user.id)

        get_score(school_id=None, db=db_session)  # ne lève pas

    def test_endpoint_refuses_when_user_flag_is_absent(self, db_session):
        """
        Fail-closed, contrairement au reste du moteur de droits : `_require_course_access` n'est
        appelée que depuis des routes HTTP, où `current_db_user` (dépendance de routeur, garantie
        au démarrage par core/route_guard.py) a toujours posé le drapeau. Son absence ne peut donc
        signaler qu'un câblage cassé — pas un mode système légitime, et surtout pas une raison de
        laisser passer une remise à zéro de TOUS les cours.
        """
        from backend.app.api.endpoints import reset

        # Aucun _make_user_as() : le drapeau reste absent.
        with pytest.raises(RuntimeError, match="câblage de routage"):
            reset(db=db_session)

    def test_write_endpoint_allowed_when_another_group_grants_write_without_domain(self, db_session):
        """
        Même règle de combinaison que partout ailleurs (access_domain_clause) : une seule ligne
        SANS domaine suffit à lever la restriction, y compris venue d'un autre groupe.
        """
        from backend.app.api.endpoints import reset

        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        restreint = ResGroup.create(db_session, {"name": "Écriture restreinte"})
        total = ResGroup.create(db_session, {"name": "Écriture totale"})
        restreint.update(db_session, {"user_ids": [user.id]})
        total.update(db_session, {"user_ids": [user.id]})
        IrModelAccess.create(db_session, {
            "model": "courses", "group_id": restreint.id, "perm_read": True, "perm_write": True,
            "domain": json.dumps([("divisions.students.user_id", "=", "user.id")]),
        })
        IrModelAccess.create(db_session, {
            "model": "courses", "group_id": total.id, "perm_read": True, "perm_write": True,
        })
        _make_user_as(db_session, user.id)

        assert reset(db=db_session) == {"status": "success"}


class TestDisplayNameUnchecked:
    def test_display_name_endpoint_bypasses_read_restriction(self, db_session):
        """
        Voir architecture.md, "display_name d'une relation non lisible" : un utilisateur SANS
        aucun droit de lecture sur schools doit quand même pouvoir résoudre le libellé d'une école
        référencée ailleurs (ex: pour l'affichage d'un menu déroulant) — jamais ses autres champs.
        """
        from backend.app.api.generic import make_display_name_endpoint

        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})  # mode système
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Sans droit Écoles"})
        group.update(db_session, {"user_ids": [user.id]})
        _make_user_as(db_session, user.id)

        # Confirme qu'un accès normal est bien bloqué (aucune ligne ir_model_access).
        assert School.read(db_session) == []

        endpoint = make_display_name_endpoint(School)
        result = endpoint(school.id, db_session)
        assert result == {"id": school.id, "display_name": "Collège Test"}

    def test_display_name_endpoint_404_for_unknown_id(self, db_session):
        from fastapi import HTTPException
        from backend.app.api.generic import make_display_name_endpoint

        endpoint = make_display_name_endpoint(School)
        with pytest.raises(HTTPException) as exc_info:
            endpoint(999, db_session)
        assert exc_info.value.status_code == 404


class TestAdminSeedCoverage:
    def test_every_mapped_model_has_an_admin_access_row(self, db_session):
        """
        Garde-fou structurel (voir architecture.md) : plutôt que de compter sur la mémoire pour
        créer une ligne ir_model_access par nouveau modèle, ce test échoue si un modèle (table ORM
        réelle OU TransientModel — voir le piège documenté dans seed_admin_access) n'en a pas.
        """
        from backend.app.core.init_db import seed_admin_access, _all_transient_model_subclasses
        from backend.app.models.base import TransientModel

        seed_admin_access(db_session)

        expected_tablenames = {
            mapper.class_.__tablename__ for mapper in Base.registry.mappers
            if getattr(mapper.class_, "__tablename__", None)
        }
        expected_tablenames |= {
            sub.__tablename__ for sub in _all_transient_model_subclasses(TransientModel)
            if getattr(sub, "__tablename__", None)
        }
        seeded_tablenames = {row[0] for row in db_session.query(IrModelAccess.model).distinct().all()}
        missing = expected_tablenames - seeded_tablenames
        assert not missing, f"Modèles mappés sans ligne ir_model_access Admin : {missing}"

        # Droits complets, sans restriction, pour chaque ligne générée.
        for access in db_session.query(IrModelAccess).all():
            assert access.perm_read and access.perm_write and access.perm_create and access.perm_unlink
            assert not access.domain


class TestNoAccessByDefault:
    def test_no_ir_model_access_row_means_no_read(self, db_session):
        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Sans droits"})
        group.update(db_session, {"user_ids": [user.id]})
        _make_user_as(db_session, user.id)

        assert School.read(db_session) == []
        assert School.count(db_session) == 0

    def test_no_ir_model_access_row_means_no_write(self, db_session):
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group = ResGroup.create(db_session, {"name": "Sans droits"})
        group.update(db_session, {"user_ids": [user.id]})
        _make_user_as(db_session, user.id)

        with pytest.raises(AccessDeniedError):
            School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})

    def test_system_mode_unaffected_when_no_user_set(self, db_session):
        # db.klepsydrix_user_id jamais posé (comportement par défaut de toute la suite existante,
        # voir P1-P3) : aucun filtrage, exactement comme avant l'introduction du moteur de droits.
        School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        assert len(School.read(db_session)) == 1


class TestUnrestrictedAccess:
    def test_read_write_grant_without_domain_gives_full_access(self, db_session):
        user = User.create(db_session, {"first_name": "Admin", "last_name": "Test", "email": None})
        group = ResGroup.create(db_session, {"name": "Admin Écoles"})
        group.update(db_session, {"user_ids": [user.id]})
        IrModelAccess.create(db_session, {
            "model": "schools", "group_id": group.id,
            "perm_read": True, "perm_write": True, "perm_create": True, "perm_unlink": True,
        })
        _make_user_as(db_session, user.id)

        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        assert len(School.read(db_session)) == 1
        school.update(db_session, {"name": "Collège Renommé"})
        school.delete(db_session)
        assert School.read(db_session) == []


class TestGroupInheritance:
    def test_implied_group_grants_access_transitively(self, db_session):
        School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})  # mode système
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        base_group = ResGroup.create(db_session, {"name": "Lecture Écoles"})
        IrModelAccess.create(db_session, {"model": "schools", "group_id": base_group.id, "perm_read": True})
        parent_group = ResGroup.create(db_session, {"name": "Groupe Parent"})
        parent_group.update(db_session, {"implied_group_ids": [base_group.id], "user_ids": [user.id]})

        _make_user_as(db_session, user.id)
        # user n'est membre QUE de parent_group, mais hérite du droit de lecture de base_group.
        assert len(School.read(db_session)) == 1


class TestDomainRestriction:
    def test_student_sees_only_own_courses_via_domain(self, db_session):
        """Cas d'usage cible du plan : groupe "Élève - Voir mon EDT seulement"."""
        student, own_course, other_course = _make_student_with_course(db_session)
        user = User.create(db_session, {"first_name": "Léa", "last_name": "Martin", "email": None})
        student.update(db_session, {"user_id": user.id})

        group = ResGroup.create(db_session, {"name": "Élève - Voir mon EDT seulement"})
        group.update(db_session, {"user_ids": [user.id]})
        domain = json.dumps(["|",
            ("class_parts.students.user_id", "=", "user.id"),
            ("divisions.students.user_id", "=", "user.id"),
        ])
        IrModelAccess.create(db_session, {"model": "courses", "group_id": group.id, "perm_read": True, "domain": domain})

        _make_user_as(db_session, user.id)
        visible = Course.read(db_session)
        assert [c.id for c in visible] == [own_course.id]
        assert Course.count(db_session) == 1

    def test_write_denied_on_record_outside_domain(self, db_session):
        student, own_course, other_course = _make_student_with_course(db_session)
        user = User.create(db_session, {"first_name": "Léa", "last_name": "Martin", "email": None})
        student.update(db_session, {"user_id": user.id})

        group = ResGroup.create(db_session, {"name": "Élève - Modifier mon EDT"})
        group.update(db_session, {"user_ids": [user.id]})
        domain = json.dumps([("divisions.students.user_id", "=", "user.id")])
        IrModelAccess.create(db_session, {"model": "courses", "group_id": group.id, "perm_read": True, "perm_write": True, "domain": domain})

        _make_user_as(db_session, user.id)
        own_course.update(db_session, {"memo": "ok"})  # dans le domaine : autorisé

        with pytest.raises(AccessDeniedError):
            other_course.update(db_session, {"memo": "refusé"})

    def test_any_row_without_domain_overrides_restrictive_rows(self, db_session):
        """Une ligne SANS domaine dans un AUTRE groupe suffit à lever toute restriction (OR)."""
        student, own_course, other_course = _make_student_with_course(db_session)
        user = User.create(db_session, {"first_name": "Léa", "last_name": "Martin", "email": None})
        student.update(db_session, {"user_id": user.id})

        restricted_group = ResGroup.create(db_session, {"name": "Restreint"})
        unrestricted_group = ResGroup.create(db_session, {"name": "Sans restriction"})
        restricted_group.update(db_session, {"user_ids": [user.id]})
        unrestricted_group.update(db_session, {"user_ids": [user.id]})
        IrModelAccess.create(db_session, {
            "model": "courses", "group_id": restricted_group.id, "perm_read": True,
            "domain": json.dumps([("divisions.students.user_id", "=", "user.id")]),
        })
        IrModelAccess.create(db_session, {"model": "courses", "group_id": unrestricted_group.id, "perm_read": True})

        _make_user_as(db_session, user.id)
        visible = Course.read(db_session)
        assert {c.id for c in visible} == {own_course.id, other_course.id}

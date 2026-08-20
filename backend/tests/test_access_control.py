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


class TestBrowse:
    """
    `CRUDMixin.browse()` — lecture par identifiants DÉSIGNÉS, par opposition à `read()` qui répond
    à une recherche (voir base.py::browse, architecture.md). Le filtrage silencieux de `read()` est
    correct sur une recherche, et dangereux sur une désignation : il produirait un résultat
    incomplet d'apparence complète.
    """
    def _restricted_user_with_two_courses(self, db):
        """Un élève dont le domaine ne couvre QUE le cours de sa division, plus un cours étranger."""
        student, own_course, foreign_course = _make_student_with_course(db)
        user = User.create(db, {"first_name": "Léa", "last_name": "Martin", "email": None})
        student.update(db, {"user_id": user.id})
        group = ResGroup.create(db, {"name": "Élève"})
        group.update(db, {"user_ids": [user.id]})
        IrModelAccess.create(db, {
            "model": "courses", "group_id": group.id, "perm_read": True,
            "domain": json.dumps([("divisions.students.user_id", "=", "user.id")]),
        })
        _make_user_as(db, user.id)
        return own_course, foreign_course

    def test_browse_returns_records_when_all_are_accessible(self, db_session):
        own_course, _ = self._restricted_user_with_two_courses(db_session)
        assert [c.id for c in Course.browse(db_session, [own_course.id])] == [own_course.id]

    def test_browse_raises_when_one_id_is_outside_the_domain(self, db_session):
        """
        Le cœur du mécanisme : `read()` renverrait ici 1 cours sur 2 demandés, silencieusement.
        `browse()` refuse — c'est ce qui empêche un PDF/export d'être amputé sans que personne
        ne le sache.
        """
        own_course, foreign_course = self._restricted_user_with_two_courses(db_session)

        # Confirme d'abord que read() tronque bien en silence, pour que le test documente le
        # contraste plutôt que seulement le nouveau comportement.
        assert len(Course.read(db_session, domain={"id": [own_course.id, foreign_course.id]})) == 1

        with pytest.raises(AccessDeniedError):
            Course.browse(db_session, [own_course.id, foreign_course.id])

    def test_browse_raises_on_nonexistent_id_without_distinguishing_it(self, db_session):
        """Inexistant et hors domaine donnent le même refus : ne jamais confirmer une existence."""
        own_course, _ = self._restricted_user_with_two_courses(db_session)
        with pytest.raises(AccessDeniedError) as exc_info:
            Course.browse(db_session, [own_course.id, 999999])
        assert "999999" not in str(exc_info.value)

    def test_browse_deduplicates_ids(self, db_session):
        """Sans dédoublonnage, browse([1, 1]) échouerait toujours (2 demandés, 1 obtenu)."""
        own_course, _ = self._restricted_user_with_two_courses(db_session)
        assert [c.id for c in Course.browse(db_session, [own_course.id, own_course.id])] == [own_course.id]

    def test_browse_preserves_requested_order(self, db_session):
        """
        Ordre DEMANDÉ, pas `__default_order__` : sur un lot désigné (imprimer des classes dans
        l'ordre coché), c'est l'ordre de l'appelant qui fait foi.
        """
        school = School.create(db_session, {"uai": "1234567B", "name": "Collège Ordre"})
        divisions = [
            Division.create(db_session, {"code": f"6{lettre}", "name": f"6ème {lettre}", "school_id": school.id})
            for lettre in ("A", "B", "C")
        ]
        ids_desordre = [divisions[2].id, divisions[0].id, divisions[1].id]
        assert [d.id for d in Division.browse(db_session, ids_desordre)] == ids_desordre

    def test_browse_on_empty_list_returns_empty(self, db_session):
        assert Course.browse(db_session, []) == []


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


class TestSystemGeneratedProtection:
    """ResGroup/IrModelAccess.is_system_generated — même patron que Partition.is_system_generated
    (models/group.py), voir models/access.py."""

    def test_cannot_create_res_group_flagged_system_without_sentinel(self, db_session):
        with pytest.raises(ValueError, match="positionné que par le système"):
            ResGroup.create(db_session, {"name": "Faux Admin", "is_system_generated": True})

    def test_cannot_create_ir_model_access_flagged_system_without_sentinel(self, db_session):
        group = ResGroup.create(db_session, {"name": "G"})
        with pytest.raises(ValueError, match="positionné que par le système"):
            IrModelAccess.create(db_session, {
                "model": "schools", "group_id": group.id, "perm_read": True, "is_system_generated": True,
            })

    def test_cannot_rename_a_system_generated_group(self, db_session):
        group = ResGroup.create(db_session, {"name": "Admin", "is_system_generated": True, "_system_write": True})
        with pytest.raises(ValueError, match="seule son appartenance"):
            group.update(db_session, {"name": "Renommé"})

    def test_can_still_update_membership_of_a_system_generated_group(self, db_session):
        group = ResGroup.create(db_session, {"name": "Admin", "is_system_generated": True, "_system_write": True})
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group.update(db_session, {"user_ids": [user.id]})  # ne lève pas
        assert [u.id for u in group.users] == [user.id]

    def test_cannot_delete_a_system_generated_group(self, db_session):
        group = ResGroup.create(db_session, {"name": "Admin", "is_system_generated": True, "_system_write": True})
        with pytest.raises(ValueError, match="ne peut pas être supprimé"):
            group.delete(db_session)

    def test_cannot_flip_is_system_generated_on_a_group_via_update(self, db_session):
        group = ResGroup.create(db_session, {"name": "G"})
        with pytest.raises(ValueError, match="ne peut être modifié que par le système"):
            group.update(db_session, {"is_system_generated": True})

    def test_cannot_modify_a_system_generated_access_row(self, db_session):
        group = ResGroup.create(db_session, {"name": "Admin", "is_system_generated": True, "_system_write": True})
        access = IrModelAccess.create(db_session, {
            "model": "schools", "group_id": group.id, "perm_read": True, "is_system_generated": True, "_system_write": True,
        })
        with pytest.raises(ValueError, match="ne peut pas être modifié"):
            access.update(db_session, {"perm_write": True})

    def test_cannot_delete_a_system_generated_access_row(self, db_session):
        group = ResGroup.create(db_session, {"name": "Admin", "is_system_generated": True, "_system_write": True})
        access = IrModelAccess.create(db_session, {
            "model": "schools", "group_id": group.id, "perm_read": True, "is_system_generated": True, "_system_write": True,
        })
        with pytest.raises(ValueError, match="ne peut pas être supprimé"):
            access.delete(db_session)

    def test_ordinary_group_and_access_remain_fully_editable(self, db_session):
        """Contrepartie : rien de tout ceci ne s'applique à un groupe/droit ordinaire (is_system_generated=False, comportement historique inchangé)."""
        group = ResGroup.create(db_session, {"name": "G"})
        group.update(db_session, {"name": "G renommé"})
        access = IrModelAccess.create(db_session, {"model": "schools", "group_id": group.id, "perm_read": True})
        access.update(db_session, {"perm_write": True})
        access.delete(db_session)
        group.delete(db_session)


class TestLastAdminGuard:
    """Refus de vider le groupe "Admin" de son dernier membre — par les 3 voies possibles (voir
    models/access.py::ResGroup.update, models/user.py::User.update/delete)."""

    def _admin_group(self, db):
        return ResGroup.create(db, {"name": "Admin", "is_system_generated": True, "_system_write": True})

    def test_cannot_empty_admin_group_via_group_update(self, db_session):
        admin_group = self._admin_group(db_session)
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        admin_group.update(db_session, {"user_ids": [user.id]})

        with pytest.raises(ValueError, match="dernier utilisateur du groupe Admin"):
            admin_group.update(db_session, {"user_ids": []})

    def test_can_remove_a_member_via_group_update_when_not_the_last(self, db_session):
        admin_group = self._admin_group(db_session)
        user1 = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        user2 = User.create(db_session, {"first_name": "B", "last_name": "B", "email": None})
        admin_group.update(db_session, {"user_ids": [user1.id, user2.id]})

        admin_group.update(db_session, {"user_ids": [user1.id]})  # ne lève pas
        assert [u.id for u in admin_group.users] == [user1.id]

    def test_cannot_remove_last_admin_via_user_update(self, db_session):
        admin_group = self._admin_group(db_session)
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        admin_group.update(db_session, {"user_ids": [user.id]})

        with pytest.raises(ValueError, match="dernier utilisateur du groupe Admin"):
            user.update(db_session, {"group_ids": []})

    def test_can_remove_a_group_from_user_when_not_the_last_admin(self, db_session):
        admin_group = self._admin_group(db_session)
        user1 = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        user2 = User.create(db_session, {"first_name": "B", "last_name": "B", "email": None})
        admin_group.update(db_session, {"user_ids": [user1.id, user2.id]})

        user1.update(db_session, {"group_ids": []})  # ne lève pas : user2 reste
        db_session.refresh(admin_group)
        assert [u.id for u in admin_group.users] == [user2.id]

    def test_cannot_delete_the_last_admin_user(self, db_session):
        admin_group = self._admin_group(db_session)
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        admin_group.update(db_session, {"user_ids": [user.id]})

        with pytest.raises(ValueError, match="dernier utilisateur du groupe Admin"):
            user.delete(db_session)

    def test_can_delete_a_non_last_admin_user(self, db_session):
        admin_group = self._admin_group(db_session)
        user1 = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        user2 = User.create(db_session, {"first_name": "B", "last_name": "B", "email": None})
        admin_group.update(db_session, {"user_ids": [user1.id, user2.id]})

        user1.delete(db_session)  # ne lève pas : user2 reste
        db_session.refresh(admin_group)
        assert [u.id for u in admin_group.users] == [user2.id]

    def test_deleting_a_person_record_linked_to_the_last_admin_is_blocked(self, db_session):
        """HasUserAccount.delete() (Teacher/Student/...) route par User.delete() — même garde-fou."""
        from backend.app.models import Teacher

        admin_group = self._admin_group(db_session)
        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        admin_group.update(db_session, {"user_ids": [user.id]})
        teacher = Teacher.create(db_session, {"code": "T1", "first_name": "A", "last_name": "A", "school_id": school.id, "user_id": user.id})

        with pytest.raises(ValueError, match="dernier utilisateur du groupe Admin"):
            teacher.delete(db_session)

    def test_unrelated_group_named_differently_is_not_protected(self, db_session):
        """Le garde-fou cible spécifiquement le groupe nommé "Admin" — un groupe ordinaire, même
        réduit à un seul membre, reste librement modifiable."""
        group = ResGroup.create(db_session, {"name": "Pas Admin"})
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        group.update(db_session, {"user_ids": [user.id]})
        group.update(db_session, {"user_ids": []})  # ne lève pas


class TestReadonlySeedCoverage:
    """seed_readonly_access (init_db.py) — miroir de TestAdminSeedCoverage, avec l'exclusion des
    tables sensibles (SECURITY_SENSITIVE_TABLENAMES)."""

    def test_consultation_group_is_read_only_on_all_non_sensitive_models(self, db_session):
        from backend.app.core.init_db import seed_readonly_access, SECURITY_SENSITIVE_TABLENAMES, _all_tablenames

        seed_readonly_access(db_session)

        expected_tablenames = set(_all_tablenames()) - SECURITY_SENSITIVE_TABLENAMES
        seeded_tablenames = {row[0] for row in db_session.query(IrModelAccess.model).distinct().all()}
        assert expected_tablenames.issubset(seeded_tablenames)

        for access in db_session.query(IrModelAccess).all():
            assert access.perm_read is True
            assert access.perm_write is False
            assert access.perm_create is False
            assert access.perm_unlink is False
            assert access.is_system_generated is True

    def test_consultation_group_has_no_access_row_at_all_for_sensitive_models(self, db_session):
        from backend.app.core.init_db import seed_readonly_access, SECURITY_SENSITIVE_TABLENAMES

        seed_readonly_access(db_session)
        seeded_tablenames = {row[0] for row in db_session.query(IrModelAccess.model).distinct().all()}
        assert not (SECURITY_SENSITIVE_TABLENAMES & seeded_tablenames)

    def test_consultation_member_can_read_but_not_write(self, db_session):
        from backend.app.core.init_db import seed_readonly_access

        seed_readonly_access(db_session)
        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})  # mode système
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        consultation_group = db_session.query(ResGroup).filter(ResGroup.name == "Consultation").first()
        consultation_group.update(db_session, {"user_ids": [user.id]})

        _make_user_as(db_session, user.id)
        assert len(School.read(db_session)) == 1
        with pytest.raises(AccessDeniedError):
            school.update(db_session, {"name": "Renommé"})

    def test_consultation_member_cannot_read_users_or_groups(self, db_session):
        from backend.app.core.init_db import seed_readonly_access

        seed_readonly_access(db_session)
        user = User.create(db_session, {"first_name": "A", "last_name": "A", "email": None})
        consultation_group = db_session.query(ResGroup).filter(ResGroup.name == "Consultation").first()
        consultation_group.update(db_session, {"user_ids": [user.id]})

        _make_user_as(db_session, user.id)
        assert User.read(db_session) == []
        assert ResGroup.read(db_session) == []


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

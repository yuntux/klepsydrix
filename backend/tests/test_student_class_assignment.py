"""
Tests pour les critères de répartition ajoutés à Student (scores, ville calculée, projets
d'accompagnement), StudentGroupingConstraint (regrouper/séparer) et le wizard d'affectation aux
classes (backend/app/models/wizard_student_class_assignment.py).
"""
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Discipline, Subject, Mef, MefDivision, Division, Student, SystemSetting, RefGrade,
    Parent, RefLegalGuardian, RefCity, RefAccompanimentProjectType,
)
from backend.app.models.student import StudentParentLink, StudentAccompanimentProject
from backend.app.models.student_grouping_constraint import StudentGroupingConstraint, StudentGroupingConstraintType
from backend.app.models.wizard_student_class_assignment import (
    _compute_class_assignment_plan, _apply_class_assignment_plan, WizardStudentClassAssignment,
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


def _make_scaffold(db, division_count=2, forecast_per_division=2):
    """École + niveau 6ème + MEF + N divisions liées, chacune avec un effectif prévisionnel."""
    school = School.create(db, {"uai": "1234567A", "name": "Collège Test"})
    ref_grade = RefGrade.create(db, {"name": "6EME"})
    mef = Mef.create(db, {
        "school_id": school.id, "code_national": "MEF_TEST", "name": "6EME", "ref_grade_id": ref_grade.id,
        "max_students_per_class": 30, "forecast_student_count": division_count * forecast_per_division,
    })
    divisions = []
    for i in range(division_count):
        code = f"6{chr(65 + i)}"
        division = Division.create(db, {"code": code, "name": f"6ème {chr(65 + i)}", "school_id": school.id})
        MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": forecast_per_division})
        divisions.append(division)
    return school, ref_grade, mef, divisions


def _make_student(db, division, mef, first_name="A", last_name="B", **extra):
    vals = {"first_name": first_name, "last_name": last_name, "division_id": division.id, "mef_id": mef.id}
    vals.update(extra)
    return Student.create(db, vals)


def _default_criteria() -> dict:
    """Tous les critères désactivés — utile pour isoler le comportement testé (répartition par
    effectif seule, ou une seule contrainte GROUP/SEPARATE)."""
    from backend.app.models.wizard_student_class_assignment import CRITERIA
    return {f"{key}_mode": "ignore" for key, _, _ in CRITERIA}


class TestStudentScoreFields:
    def test_accepts_score_within_range(self, db_session):
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        student = _make_student(db_session, div_a, mef, attendance_score=8, academic_score=5, behavior_score=10)
        assert student.attendance_score == 8

    def test_accepts_null_score_as_not_evaluated(self, db_session):
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        student = _make_student(db_session, div_a, mef)
        assert student.academic_score is None

    def test_rejects_score_out_of_range(self, db_session):
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        with pytest.raises(ValueError, match="entre 1 et 10"):
            _make_student(db_session, div_a, mef, behavior_score=11)

    def test_rejects_score_zero(self, db_session):
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        with pytest.raises(ValueError, match="entre 1 et 10"):
            _make_student(db_session, div_a, mef, attendance_score=0)


class TestCriterionCityId:
    def test_prefers_legal_guardian_one(self, db_session):
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        student = _make_student(db_session, div_a, mef)
        city_1 = RefCity.create(db_session, {"name": "Lyon"})
        city_2 = RefCity.create(db_session, {"name": "Paris"})
        guardian_1 = RefLegalGuardian.create(db_session, {"code": "1", "name": "Responsable légal 1"})
        guardian_2 = RefLegalGuardian.create(db_session, {"code": "2", "name": "Responsable légal 2"})
        parent_1 = Parent.create(db_session, {"first_name": "P1", "last_name": "X", "address_city_id": city_1.id})
        parent_2 = Parent.create(db_session, {"first_name": "P2", "last_name": "Y", "address_city_id": city_2.id})
        # Rattaché en second mais responsable légal 1 : doit quand même l'emporter.
        StudentParentLink.create(db_session, {"student_id": student.id, "parent_id": parent_2.id, "legal_guardian_id": guardian_2.id})
        StudentParentLink.create(db_session, {"student_id": student.id, "parent_id": parent_1.id, "legal_guardian_id": guardian_1.id})

        assert student.criterion_city_id == city_1.id

    def test_falls_back_to_first_parent_without_legal_guardian(self, db_session):
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        student = _make_student(db_session, div_a, mef)
        city = RefCity.create(db_session, {"name": "Marseille"})
        parent = Parent.create(db_session, {"first_name": "P", "last_name": "X", "address_city_id": city.id})
        StudentParentLink.create(db_session, {"student_id": student.id, "parent_id": parent.id})

        assert student.criterion_city_id == city.id

    def test_none_without_any_parent(self, db_session):
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        student = _make_student(db_session, div_a, mef)
        assert student.criterion_city_id is None


class TestStudentAccompanimentProject:
    def test_creates_project_for_student(self, db_session):
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        student = _make_student(db_session, div_a, mef)
        project_type = RefAccompanimentProjectType.create(db_session, {"code": "PAP", "name": "Plan d'Accompagnement Personnalisé"})

        project = StudentAccompanimentProject.create(db_session, {"student_id": student.id, "project_type_id": project_type.id})

        assert project in student.accompaniment_projects

    def test_rejects_end_date_before_start_date(self, db_session):
        from datetime import date
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        student = _make_student(db_session, div_a, mef)
        project_type = RefAccompanimentProjectType.create(db_session, {"code": "PAI", "name": "Projet d'Accueil Individualisé"})

        with pytest.raises(ValueError, match="postérieure"):
            StudentAccompanimentProject.create(db_session, {
                "student_id": student.id, "project_type_id": project_type.id,
                "start_date": date(2026, 9, 1), "end_date": date(2026, 8, 1),
            })


class TestStudentGroupingConstraint:
    def test_rejects_single_student(self, db_session):
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        student = _make_student(db_session, div_a, mef)

        with pytest.raises(ValueError, match="au moins deux élèves"):
            StudentGroupingConstraint.create(db_session, {
                "name": "Fratrie", "constraint_type": "group", "student_ids": [student.id],
            })

    def test_accepts_two_students(self, db_session):
        _, _, mef, (div_a, _) = _make_scaffold(db_session)
        s1 = _make_student(db_session, div_a, mef, first_name="E1")
        s2 = _make_student(db_session, div_a, mef, first_name="E2")

        constraint = StudentGroupingConstraint.create(db_session, {
            "name": "Fratrie", "constraint_type": "group", "student_ids": [s1.id, s2.id],
        })
        assert len(constraint.students) == 2


class TestComputeClassAssignmentPlan:
    def test_raises_when_no_division_linked(self, db_session):
        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        ref_grade = RefGrade.create(db_session, {"name": "6EME"})
        Mef.create(db_session, {
            "school_id": school.id, "code_national": "MEF_TEST", "name": "6EME", "ref_grade_id": ref_grade.id,
            "max_students_per_class": 30,
        })
        with pytest.raises(ValueError, match="Aucune division"):
            _compute_class_assignment_plan(db_session, ref_grade.id, _default_criteria())

    def test_distributes_students_evenly_across_divisions_with_no_active_criteria(self, db_session):
        """Tous les critères ignorés : le glouton se rabat sur l'équilibrage pur des effectifs
        (tie-break sur le compte courant, voir score_for/max)."""
        _, ref_grade, mef, (div_a, div_b) = _make_scaffold(db_session, division_count=2, forecast_per_division=2)
        for i in range(4):
            _make_student(db_session, div_a, mef, first_name=f"E{i}")

        plan = _compute_class_assignment_plan(db_session, ref_grade.id, _default_criteria())

        assert plan["division_count"][div_a.id] == 2
        assert plan["division_count"][div_b.id] == 2
        assert not plan["warnings"]

    def test_spread_gender_balances_across_divisions(self, db_session):
        _, ref_grade, mef, (div_a, div_b) = _make_scaffold(db_session, division_count=2, forecast_per_division=3)
        for i in range(3):
            _make_student(db_session, div_a, mef, first_name=f"M{i}", gender="M")
        for i in range(3):
            _make_student(db_session, div_a, mef, first_name=f"F{i}", gender="F")

        criteria = _default_criteria()
        criteria["gender_mode"] = "spread_3"
        plan = _compute_class_assignment_plan(db_session, ref_grade.id, criteria)

        # Chaque division doit recevoir un mélange, pas tous les garçons (ou toutes les filles) d'un côté.
        buckets_by_division = {div_a.id: [], div_b.id: []}
        for sid, did in plan["assignments"].items():
            buckets_by_division[did].append(plan["students_by_id"][sid].gender.value)
        assert "M" in buckets_by_division[div_a.id] and "F" in buckets_by_division[div_a.id]
        assert "M" in buckets_by_division[div_b.id] and "F" in buckets_by_division[div_b.id]

    def test_group_constraint_keeps_students_together(self, db_session):
        _, ref_grade, mef, (div_a, div_b) = _make_scaffold(db_session, division_count=2, forecast_per_division=3)
        s1 = _make_student(db_session, div_a, mef, first_name="E1")
        s2 = _make_student(db_session, div_a, mef, first_name="E2")
        for i in range(4):
            _make_student(db_session, div_a, mef, first_name=f"O{i}")
        StudentGroupingConstraint.create(db_session, {
            "name": "À regrouper", "constraint_type": "group", "student_ids": [s1.id, s2.id],
        })

        plan = _compute_class_assignment_plan(db_session, ref_grade.id, _default_criteria())

        assert plan["assignments"][s1.id] == plan["assignments"][s2.id]

    def test_separate_constraint_splits_students_apart(self, db_session):
        _, ref_grade, mef, (div_a, div_b) = _make_scaffold(db_session, division_count=2, forecast_per_division=3)
        s1 = _make_student(db_session, div_a, mef, first_name="E1")
        s2 = _make_student(db_session, div_a, mef, first_name="E2")
        StudentGroupingConstraint.create(db_session, {
            "name": "À séparer", "constraint_type": "separate", "student_ids": [s1.id, s2.id],
        })

        plan = _compute_class_assignment_plan(db_session, ref_grade.id, _default_criteria())

        assert plan["assignments"][s1.id] != plan["assignments"][s2.id]
        assert not plan["warnings"]

    def test_warns_when_forecast_capacity_is_exceeded(self, db_session):
        _, ref_grade, mef, (div_a,) = _make_scaffold(db_session, division_count=1, forecast_per_division=1)
        for i in range(3):
            _make_student(db_session, div_a, mef, first_name=f"E{i}")

        plan = _compute_class_assignment_plan(db_session, ref_grade.id, _default_criteria())

        assert any("Effectif prévisionnel dépassé" in w for w in plan["warnings"])


class TestApplyClassAssignmentPlan:
    def test_writes_division_id_and_counts_changes(self, db_session):
        _, ref_grade, mef, (div_a, div_b) = _make_scaffold(db_session, division_count=2, forecast_per_division=2)
        for i in range(4):
            _make_student(db_session, div_a, mef, first_name=f"E{i}")

        plan = _compute_class_assignment_plan(db_session, ref_grade.id, _default_criteria())
        result = _apply_class_assignment_plan(db_session, plan)

        assert result["assigned_count"] == 4
        moved_to_b = db_session.query(Student).filter(Student.division_id == div_b.id).count()
        assert moved_to_b == 2
        assert result["changed_count"] == moved_to_b  # seuls les élèves déplacés vers div_b ont changé


class TestWizardStudentClassAssignment:
    def test_rpc_preview_is_read_only(self, db_session):
        _, ref_grade, mef, (div_a, div_b) = _make_scaffold(db_session, division_count=2, forecast_per_division=2)
        for i in range(4):
            _make_student(db_session, div_a, mef, first_name=f"E{i}")
        wizard = WizardStudentClassAssignment(id=1)

        result = wizard.rpc_preview(db_session, ref_grade.id, **_default_criteria())

        assert all(s.division_id == div_a.id for s in db_session.query(Student).all())
        assert len(result["division_rows"]) == 2

    def test_rpc_generate_applies_assignment(self, db_session):
        _, ref_grade, mef, (div_a, div_b) = _make_scaffold(db_session, division_count=2, forecast_per_division=2)
        for i in range(4):
            _make_student(db_session, div_a, mef, first_name=f"E{i}")
        wizard = WizardStudentClassAssignment(id=1)

        result = wizard.rpc_generate(db_session, ref_grade.id, **_default_criteria())

        assert "réaffecté" in result["result_html"]
        assigned_divisions = {s.division_id for s in db_session.query(Student).all()}
        assert assigned_divisions == {div_a.id, div_b.id}

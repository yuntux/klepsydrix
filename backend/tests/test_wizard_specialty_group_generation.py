"""
Tests pour les enseignements de spécialité (réforme du lycée) : StudentSpecialtyChoice,
SpecialtyGroupConfig, l'unicité MefService(mef_id, subject_id), et le wizard de génération des
groupes (backend/app/models/wizard_specialty_group_generation.py).
"""
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Discipline, Subject, Mef, MefDivision, Division, Student, SystemSetting, Course, RefGrade,
)
from backend.app.models.mef import MefService
from backend.app.models.student import StudentSpecialtyChoice
from backend.app.models.specialty_group_config import SpecialtyGroupConfig
from backend.app.models.group import Group
from backend.app.models.service import Service
from backend.app.models.wizard_course_generation import generate_courses_from_services
from backend.app.models.wizard_specialty_group_generation import (
    _compute_specialty_plan, _apply_specialty_plan, WizardSpecialtyGroupGeneration,
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


def _make_1ere_scaffold(db, limit=3):
    """École + niveau 1ère (specialty_choice_limit=limit) + MEF + 2 divisions liées."""
    school = School.create(db, {"uai": "1234567A", "name": "Lycée Test"})
    ref_grade = RefGrade.create(db, {"name": "1ERE", "specialty_choice_limit": limit})
    mef = Mef.create(db, {"school_id": school.id, "code_national": "20010012111", "name": "1ERE GENERALE", "ref_grade_id": ref_grade.id, "max_students_per_class": 35, "forecast_student_count": 64})
    div_a = Division.create(db, {"school_id": school.id, "code": "1A", "name": "1ère A", "student_count": 32})
    div_b = Division.create(db, {"school_id": school.id, "code": "1B", "name": "1ère B", "student_count": 32})
    MefDivision.create(db, {"mef_id": mef.id, "division_id": div_a.id, "forecast_student_count": 32})
    MefDivision.create(db, {"mef_id": mef.id, "division_id": div_b.id, "forecast_student_count": 32})
    return school, ref_grade, mef, div_a, div_b


def _make_specialty_subject(db, discipline, code, is_specialty=True):
    return Subject.create(db, {"code": code, "code_nomenclature": f"N_{code}", "short_name": code, "name": f"Spécialité {code}", "discipline_id": discipline.id, "is_specialty": is_specialty})


def _make_student(db, division, mef, first_name="A", last_name="B"):
    return Student.create(db, {"first_name": first_name, "last_name": last_name, "division_id": division.id, "mef_id": mef.id})


class TestStudentSpecialtyChoice:
    def test_allows_non_specialty_subject_without_counting_toward_limit(self, db_session):
        """
        Depuis l'import SIECLE des options élève (OPTIONS_ELEVE), StudentSpecialtyChoice porte
        aussi bien une LV2 de collège ou une option facultative qu'une spécialité de lycée — voir
        student.py. Seules les matières is_specialty=True sont plafonnées par
        RefGrade.specialty_choice_limit ; une matière ordinaire ne consomme pas ce quota et ne
        doit jamais être rejetée pour cette raison.
        """
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = Subject.create(db_session, {"code": "EPS", "code_nomenclature": "N_EPS", "short_name": "EPS", "name": "EPS", "discipline_id": discipline.id, "is_specialty": False})
        _, _, mef, div_a, _ = _make_1ere_scaffold(db_session)
        student = _make_student(db_session, div_a, mef)

        choice = StudentSpecialtyChoice.create(db_session, {"student_id": student.id, "subject_id": subject.id, "rank": 1})
        assert choice.subject_id == subject.id

    def test_rejects_specialty_choice_beyond_grade_limit(self, db_session):
        """Le plafond compte les matières is_specialty=True déjà rattachées à l'élève, pas le rang
        de la ligne en cours de création (voir _check_specialty_count_within_grade_limit)."""
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        _, _, mef, div_a, _ = _make_1ere_scaffold(db_session, limit=3)
        student = _make_student(db_session, div_a, mef)
        for i in range(3):
            subject = _make_specialty_subject(db_session, discipline, f"MATH{i}")
            StudentSpecialtyChoice.create(db_session, {"student_id": student.id, "subject_id": subject.id, "rank": i + 1})

        matiere_en_trop = _make_specialty_subject(db_session, discipline, "MATH3")
        with pytest.raises(ValueError, match="plafond"):
            StudentSpecialtyChoice.create(db_session, {"student_id": student.id, "subject_id": matiere_en_trop.id, "rank": 4})

    def test_rejects_when_grade_has_no_limit_configured(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_specialty_subject(db_session, discipline, "MATH")
        school, ref_grade, mef, div_a, _ = _make_1ere_scaffold(db_session, limit=None)
        student = _make_student(db_session, div_a, mef)

        with pytest.raises(ValueError, match="non défini"):
            StudentSpecialtyChoice.create(db_session, {"student_id": student.id, "subject_id": subject.id, "rank": 1})

    def test_rejects_duplicate_subject_for_same_student(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_specialty_subject(db_session, discipline, "MATH")
        _, _, mef, div_a, _ = _make_1ere_scaffold(db_session)
        student = _make_student(db_session, div_a, mef)
        StudentSpecialtyChoice.create(db_session, {"student_id": student.id, "subject_id": subject.id, "rank": 1})

        with pytest.raises(ValueError, match="déjà un vœu"):
            StudentSpecialtyChoice.create(db_session, {"student_id": student.id, "subject_id": subject.id, "rank": 2})


class TestSpecialtyGroupConfig:
    def test_rejects_non_specialty_subject(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = Subject.create(db_session, {"code": "EPS", "code_nomenclature": "N_EPS", "short_name": "EPS", "name": "EPS", "discipline_id": discipline.id, "is_specialty": False})
        _, ref_grade, _, _, _ = _make_1ere_scaffold(db_session)

        with pytest.raises(ValueError, match="Matière de Spécialité"):
            SpecialtyGroupConfig.create(db_session, {"subject_id": subject.id, "ref_grade_id": ref_grade.id, "max_students_per_group": 12})

    def test_rejects_non_positive_threshold(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_specialty_subject(db_session, discipline, "MATH")
        _, ref_grade, _, _, _ = _make_1ere_scaffold(db_session)

        with pytest.raises(ValueError, match="supérieur à 0"):
            SpecialtyGroupConfig.create(db_session, {"subject_id": subject.id, "ref_grade_id": ref_grade.id, "max_students_per_group": 0})

    def test_rejects_duplicate_subject_ref_grade_pair(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_specialty_subject(db_session, discipline, "MATH")
        _, ref_grade, _, _, _ = _make_1ere_scaffold(db_session)
        SpecialtyGroupConfig.create(db_session, {"subject_id": subject.id, "ref_grade_id": ref_grade.id, "max_students_per_group": 12})

        with pytest.raises(ValueError, match="existe déjà"):
            SpecialtyGroupConfig.create(db_session, {"subject_id": subject.id, "ref_grade_id": ref_grade.id, "max_students_per_group": 15})


class TestMefServiceUniqueness:
    def test_rejects_duplicate_mef_subject_pair(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_specialty_subject(db_session, discipline, "MATH")
        _, _, mef, _, _ = _make_1ere_scaffold(db_session)
        MefService.create(db_session, {"mef_id": mef.id, "subject_id": subject.id})

        with pytest.raises(ValueError, match="existe déjà"):
            MefService.create(db_session, {"mef_id": mef.id, "subject_id": subject.id})


def _seed_two_specialties_four_students(db, limit=3, threshold=1):
    """
    2 matières de spécialité (MATH/SVT), 2 divisions (A/B), 4 élèves — 2 par division — répartis
    en 2 parcours différents (MATH+SVT pour tous, dans cet ordre de rang). threshold=1 force 4
    groupes par matière (1 élève par groupe) pour tester le bin-packing sur un cas simple.
    """
    discipline = Discipline.create(db, {"code": "GEN", "name": "Général"})
    subject_math = _make_specialty_subject(db, discipline, "MATH")
    subject_svt = _make_specialty_subject(db, discipline, "SVT")
    school, ref_grade, mef, div_a, div_b = _make_1ere_scaffold(db, limit=limit)

    SpecialtyGroupConfig.create(db, {"subject_id": subject_math.id, "ref_grade_id": ref_grade.id, "max_students_per_group": threshold})
    SpecialtyGroupConfig.create(db, {"subject_id": subject_svt.id, "ref_grade_id": ref_grade.id, "max_students_per_group": threshold})

    students = []
    for i, division in enumerate([div_a, div_a, div_b, div_b]):
        student = _make_student(db, division, mef, first_name=f"E{i}", last_name="X")
        StudentSpecialtyChoice.create(db, {"student_id": student.id, "subject_id": subject_math.id, "rank": 1})
        StudentSpecialtyChoice.create(db, {"student_id": student.id, "subject_id": subject_svt.id, "rank": 2})
        students.append(student)

    return {
        "school": school, "ref_grade": ref_grade, "mef": mef, "divisions": (div_a, div_b),
        "subjects": (subject_math, subject_svt), "students": students,
    }


class TestComputeSpecialtyPlan:
    def test_raises_when_grade_has_no_limit(self, db_session):
        _, ref_grade, _, _, _ = _make_1ere_scaffold(db_session, limit=None)
        with pytest.raises(ValueError, match="n'est pas configuré"):
            _compute_specialty_plan(db_session, ref_grade.id)

    def test_groups_students_by_parcours(self, db_session):
        ctx = _seed_two_specialties_four_students(db_session, threshold=4)
        plan = _compute_specialty_plan(db_session, ctx["ref_grade"].id)
        subject_math, subject_svt = ctx["subjects"]

        assert plan["parcours_counts"] == {(subject_math.id, subject_svt.id): 4}

    def test_computes_groups_needed_from_threshold(self, db_session):
        ctx = _seed_two_specialties_four_students(db_session, threshold=1)
        plan = _compute_specialty_plan(db_session, ctx["ref_grade"].id)
        subject_math, subject_svt = ctx["subjects"]

        assert len(plan["subject_bins"][subject_math.id]) == 4
        assert len(plan["subject_bins"][subject_svt.id]) == 4
        assert not plan["warnings"]

    def test_warns_and_ignores_subject_without_config(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_specialty_subject(db_session, discipline, "MATH")
        _, ref_grade, mef, div_a, _ = _make_1ere_scaffold(db_session)
        student = _make_student(db_session, div_a, mef)
        StudentSpecialtyChoice.create(db_session, {"student_id": student.id, "subject_id": subject.id, "rank": 1})

        plan = _compute_specialty_plan(db_session, ref_grade.id)

        assert subject.id not in plan["subject_bins"]
        assert any("Aucun seuil configuré" in w for w in plan["warnings"])

    def test_warns_when_max_groups_count_is_exceeded(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_specialty_subject(db_session, discipline, "MATH")
        _, ref_grade, mef, div_a, _ = _make_1ere_scaffold(db_session)
        SpecialtyGroupConfig.create(db_session, {"subject_id": subject.id, "ref_grade_id": ref_grade.id, "max_students_per_group": 1, "max_groups_count": 1})
        for i in range(3):
            student = _make_student(db_session, div_a, mef, first_name=f"E{i}", last_name="X")
            StudentSpecialtyChoice.create(db_session, {"student_id": student.id, "subject_id": subject.id, "rank": 1})

        plan = _compute_specialty_plan(db_session, ref_grade.id)

        assert len(plan["subject_bins"][subject.id]) == 1  # plafonné
        assert any("sera dépassé" in w for w in plan["warnings"])


class TestApplySpecialtyPlan:
    def test_creates_groups_services_and_repartitions(self, db_session):
        ctx = _seed_two_specialties_four_students(db_session, threshold=2)
        plan = _compute_specialty_plan(db_session, ctx["ref_grade"].id)

        result = _apply_specialty_plan(db_session, plan)

        assert result["created_groups"] == 4  # 2 matières x 2 groupes (4 élèves / seuil 2)
        assert result["created_services"] == 4
        assert db_session.query(Group).count() == 4
        assert db_session.query(Service).filter(Service.group_id.isnot(None)).count() == 4
        # Un seul MefService par matière (find-or-create), pas un par groupe
        assert db_session.query(MefService).filter(MefService.mef_id == ctx["mef"].id).count() == 2

    def test_second_run_reuses_existing_mef_service(self, db_session):
        ctx = _seed_two_specialties_four_students(db_session, threshold=2)
        plan = _compute_specialty_plan(db_session, ctx["ref_grade"].id)
        _apply_specialty_plan(db_session, plan)
        mef_service_ids_before = {ms.id for ms in db_session.query(MefService).all()}

        plan_again = _compute_specialty_plan(db_session, ctx["ref_grade"].id)
        _apply_specialty_plan(db_session, plan_again)

        mef_service_ids_after = {ms.id for ms in db_session.query(MefService).all()}
        assert mef_service_ids_before == mef_service_ids_after

    def test_generated_services_produce_courses_via_course_generation_wizard(self, db_session):
        ctx = _seed_two_specialties_four_students(db_session, threshold=2)
        plan = _compute_specialty_plan(db_session, ctx["ref_grade"].id)
        _apply_specialty_plan(db_session, plan)

        result = generate_courses_from_services(db_session)

        assert result["generated_count"] > 0
        courses_with_group = [c for c in db_session.query(Course).all() if c.groups]
        assert len(courses_with_group) > 0
        for c in courses_with_group:
            assert len(c.groups) == 1


class TestWizardSpecialtyGroupGeneration:
    def test_rpc_preview_is_read_only(self, db_session):
        ctx = _seed_two_specialties_four_students(db_session, threshold=2)
        wizard = WizardSpecialtyGroupGeneration(id=1)

        result = wizard.rpc_preview(db_session, ctx["ref_grade"].id)

        assert db_session.query(Group).count() == 0
        assert db_session.query(Service).count() == 0
        assert len(result["parcours_rows"]) == 1
        assert result["parcours_rows"][0]["student_count"] == 4
        assert len(result["groups_rows"]) == 2

    def test_rpc_generate_creates_resources_and_reports_counts(self, db_session):
        ctx = _seed_two_specialties_four_students(db_session, threshold=2)
        wizard = WizardSpecialtyGroupGeneration(id=1)

        result = wizard.rpc_generate(db_session, ctx["ref_grade"].id)

        assert "4 groupe(s)" in result["result_html"]
        assert "4 service(s)" in result["result_html"]
        assert db_session.query(Group).count() == 4

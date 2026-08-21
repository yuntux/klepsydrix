"""
Tests pour la génération en masse des Course à partir de la répartition
Service/ServiceRepartition/Alignment (voir backend/app/models/wizard_course_generation.py).
"""
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Discipline, Subject, Mef, MefDivision, Division, Teacher, Classroom,
    Group, Service, ServiceRepartition, Alignment, SystemSetting, Course, Timeslot, RefGrade,
)
from backend.app.models.mef import MefService
from backend.app.models.group import Partition, ClassPart
from backend.app.models.wizard_course_generation import generate_courses_from_services, WizardCourseGeneration
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


def _make_school_division(db, code="6A"):
    school = School.create(db, {"uai": "1234567A", "name": "Collège Test"})
    division = Division.create(db, {"school_id": school.id, "code": code, "name": f"6ème {code}", "student_count": 24})
    ref_grade = RefGrade.create(db, {"name": "6EME"})
    mef = Mef.create(db, {"school_id": school.id, "code_national": "10010012110", "name": "6EME", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 60})
    mef_division = MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 28})
    return school, division, mef, mef_division


def _make_subject(db, discipline, code):
    return Subject.create(db, {"code": code, "code_nomenclature": f"N_{code}", "short_name": code, "name": f"Matière {code}", "discipline_id": discipline.id})


def _make_service(db, mef, mef_division, subject, teachers, group_id=None, reduced_group_student_count=0):
    """Service auto-généré par MefService.create() pour le couple (mef, mef_division)."""
    if group_id is not None:
        # Un service lié à un Group (plutôt qu'à une Division) : la génération auto par
        # MefService.create() suppose une Division ; utiliser un Mef sans aucune MefDivision
        # associée évite toute auto-génération, puis créer le Service directement à la main.
        school = mef.school
        isolated_ref_grade = RefGrade.create(db, {"name": "ISOLE"})
        isolated_mef = Mef.create(db, {"school_id": school.id, "code_national": "10010012999", "name": "MEF isolé", "ref_grade_id": isolated_ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 60})
        mef_service = MefService.create(db, {"mef_id": isolated_mef.id, "subject_id": subject.id})
        service = Service.create(db, {"mef_service_id": mef_service.id, "group_id": group_id, "subject_id": subject.id, "discipline_id": mef_service.discipline_id})
    else:
        mef_service = MefService.create(db, {"mef_id": mef.id, "subject_id": subject.id})
        service = db.query(Service).filter(
            Service.mef_service_id == mef_service.id,
            Service.mef_division_id == mef_division.id,
        ).one()
    service.update(db, {"teacher_ids": [t.id for t in teachers], "reduced_group_student_count": reduced_group_student_count})
    return service


class TestFullClassService:
    def test_generates_one_simple_course_per_occurrence(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_subject(db_session, discipline, "MATH")
        school, division, mef, mef_division = _make_school_division(db_session)
        teacher = Teacher.create(db_session, {"code": "T1", "first_name": "A", "last_name": "B", "school_id": school.id})
        service = _make_service(db_session, mef, mef_division, subject, [teacher])
        ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "FULL_CLASS"})

        result = generate_courses_from_services(db_session)

        assert result["generated_count"] == 2
        courses = db_session.query(Course).all()
        assert len(courses) == 2
        for c in courses:
            assert [d.id for d in c.divisions] == [division.id]
            assert c.groups == []
            assert c.subject_id == subject.id
            assert c.week_type.value == "W"
            assert c.duration_minutes == 60


class TestSplitService:
    def test_creates_two_groups_and_alternates_occurrences(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_subject(db_session, discipline, "ANG")
        school, division, mef, mef_division = _make_school_division(db_session)
        teacher = Teacher.create(db_session, {"code": "T2", "first_name": "A", "last_name": "B", "school_id": school.id})
        service = _make_service(db_session, mef, mef_division, subject, [teacher])
        # 120min/semaine en dédoublement -> 1 ligne (60min, occurrence_count=2, group_count=2 fixe,
        # voir _generate_repartition_service/plan Volet B) : 2x2=4 Course générés, comme avant.
        service.update(db_session, {"weekly_duration_split_minutes": 120})

        result = generate_courses_from_services(db_session)

        assert result["generated_count"] == 4
        courses = db_session.query(Course).all()
        group_ids_used = {c.groups[0].id for c in courses}
        assert len(group_ids_used) == 2
        for c in courses:
            assert len(c.groups) == 1
            assert len(c.class_parts) == 1  # peuplé automatiquement via la cascade Group -> ClassPart
            assert c.class_parts[0].id in {cp.id for cp in c.groups[0].class_parts}
        # 2 occurrences par groupe (4 occurrences / 2 groupes)
        from collections import Counter
        counts = Counter(c.groups[0].id for c in courses)
        assert set(counts.values()) == {2}

        partitions = db_session.query(Partition).all()
        assert len(partitions) == 1
        assert partitions[0].special_type.value == "HALF_ALPHA"
        assert len(partitions[0].class_parts) == 2

class TestReducedService:
    def test_uses_computed_groups_need(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_subject(db_session, discipline, "SPO")
        school, division, mef, mef_division = _make_school_division(db_session)
        teacher = Teacher.create(db_session, {"code": "T4", "first_name": "A", "last_name": "B", "school_id": school.id})
        # 24 élèves / 8 par groupe reduit -> 3 groupes ; 120min/semaine -> 1 ligne (60min,
        # occurrence_count=2, group_count=3) : 2x3=6 Course générés, comme avant (plan Volet B).
        service = _make_service(db_session, mef, mef_division, subject, [teacher], reduced_group_student_count=8)
        service.update(db_session, {"student_count": 24, "weekly_duration_reduced_minutes": 120})

        result = generate_courses_from_services(db_session)

        assert result["generated_count"] == 6
        courses = db_session.query(Course).all()
        group_ids_used = {c.groups[0].id for c in courses}
        assert len(group_ids_used) == 3
        from collections import Counter
        counts = Counter(c.groups[0].id for c in courses)
        assert set(counts.values()) == {2}


class TestAlignment:
    def test_generates_composed_course_with_aggregated_resources(self, db_session):
        discipline = Discipline.create(db_session, {"code": "LV2", "name": "Langues"})
        subject_de = _make_subject(db_session, discipline, "ALL")
        subject_es = _make_subject(db_session, discipline, "ESP")
        school, division, mef, mef_division = _make_school_division(db_session)
        t_de = Teacher.create(db_session, {"code": "T_DE", "first_name": "A", "last_name": "B", "school_id": school.id})
        t_es = Teacher.create(db_session, {"code": "T_ES", "first_name": "C", "last_name": "D", "school_id": school.id})

        s_de = _make_service(db_session, mef, mef_division, subject_de, [t_de])
        s_es = _make_service(db_session, mef, mef_division, subject_es, [t_es])
        ServiceRepartition.create(db_session, {"service_id": s_de.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "FULL_CLASS"})
        ServiceRepartition.create(db_session, {"service_id": s_es.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "FULL_CLASS"})

        alignment = Alignment.create(db_session, {"code": "AL_LV2", "name": "Barrette LV2"})
        s_de.update(db_session, {"alignment_id": alignment.id})
        s_es.update(db_session, {"alignment_id": alignment.id})

        result = generate_courses_from_services(db_session)

        assert result["generated_count"] == 2
        courses = db_session.query(Course).all()
        for c in courses:
            assert c.is_composed is True
            assert c.subject_id is None  # matières différentes -> pas de matière propre
            assert {t.id for t in c.teachers} == {t_de.id, t_es.id}
            assert [d.id for d in c.divisions] == [division.id]

    def test_service_linked_to_group_is_excluded_from_aggregation(self, db_session):
        discipline = Discipline.create(db_session, {"code": "LV2", "name": "Langues"})
        subject_de = _make_subject(db_session, discipline, "ALL")
        subject_es = _make_subject(db_session, discipline, "ESP")
        school, division, mef, mef_division = _make_school_division(db_session)
        t_de = Teacher.create(db_session, {"code": "T_DE2", "first_name": "A", "last_name": "B", "school_id": school.id})
        t_es = Teacher.create(db_session, {"code": "T_ES2", "first_name": "C", "last_name": "D", "school_id": school.id})
        group = Group.create(db_session, {"name": "GRPLV2"})

        s_de = _make_service(db_session, mef, mef_division, subject_de, [t_de])
        s_es = _make_service(db_session, mef, None, subject_es, [t_es], group_id=group.id)
        ServiceRepartition.create(db_session, {"service_id": s_de.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "FULL_CLASS"})
        ServiceRepartition.create(db_session, {"service_id": s_es.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "FULL_CLASS"})

        alignment = Alignment.create(db_session, {"code": "AL_LV2B", "name": "Barrette LV2 B"})
        s_de.update(db_session, {"alignment_id": alignment.id})
        s_es.update(db_session, {"alignment_id": alignment.id})

        result = generate_courses_from_services(db_session)

        assert result["generated_count"] == 1
        course = db_session.query(Course).first()
        assert {t.id for t in course.teachers} == {t_de.id}
        assert course.subject_id == subject_de.id


class TestRegeneration:
    def test_existing_courses_are_deleted_before_regeneration(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_subject(db_session, discipline, "MATH")
        school, division, mef, mef_division = _make_school_division(db_session)
        teacher = Teacher.create(db_session, {"code": "T5", "first_name": "A", "last_name": "B", "school_id": school.id})

        timeslot = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
        parent = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "is_composed": True, "teacher_ids": [teacher.id]})
        Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "parent_id": parent.id, "duration_minutes": 30, "teacher_ids": [teacher.id]})
        pinned = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [teacher.id], "timeslot_id": timeslot.id})
        pinned.update(db_session, {"is_pinned": True})
        assert db_session.query(Course).count() == 3

        service = _make_service(db_session, mef, mef_division, subject, [teacher])
        ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 30, "periodicity": "WEEKLY", "group_type": "FULL_CLASS"})

        result = generate_courses_from_services(db_session)

        assert result["deleted_count"] == 3  # total des lignes (parent + son enfant cascadé + pinned), même métrique que info_html
        assert db_session.query(Course).count() == 1

    def test_regenerate_reuses_existing_partition_and_group(self, db_session):
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_subject(db_session, discipline, "ANG")
        school, division, mef, mef_division = _make_school_division(db_session)
        teacher = Teacher.create(db_session, {"code": "T6", "first_name": "A", "last_name": "B", "school_id": school.id})
        service = _make_service(db_session, mef, mef_division, subject, [teacher])
        ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 30, "periodicity": "WEEKLY", "group_type": "SPLIT"})

        generate_courses_from_services(db_session)
        assert db_session.query(Partition).count() == 1
        assert db_session.query(Group).count() == 2

        generate_courses_from_services(db_session)
        assert db_session.query(Partition).count() == 1
        assert db_session.query(Group).count() == 2


class TestWizardCourseGeneration:
    def test_read_reflects_existing_course_count(self, db_session):
        instances = WizardCourseGeneration.read(db_session)
        assert len(instances) == 1
        assert "seront supprimés" not in instances[0].info_html

        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        discipline = Discipline.create(db_session, {"code": "GEN", "name": "Général"})
        subject = _make_subject(db_session, discipline, "MATH")
        teacher = Teacher.create(db_session, {"code": "T7", "first_name": "A", "last_name": "B", "school_id": school.id})
        Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [teacher.id]})

        instances = WizardCourseGeneration.read(db_session)
        assert "1 cours existant" in instances[0].info_html

    def test_rpc_generate_courses_returns_result_html(self, db_session):
        wizard = WizardCourseGeneration(id=1, info_html="")
        result = wizard.rpc_generate_courses(db_session)
        assert "0 cours générés" in result["result_html"]
        # Lu par GenericWizard.vue à la fermeture pour rafraîchir le cache navigateur des Course
        # (voir advanceOrFinish) : la ressource propre du wizard n'est pas ce qui a été modifié.
        assert result["mutated_resources"] == ["courses"]

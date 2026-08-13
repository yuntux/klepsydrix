"""
Tests pour TrmdLine.read() (backend/app/models/trmd_synthesis.py, volet E) : agrégation des
besoins (MefService/Service/ServiceRepartition) et des moyens (Teacher) par Discipline.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Discipline, Subject, Mef, MefDivision, Division, Teacher, TeacherDiscipline,
    TeacherAra, RefAra, TeacherOtherSchool, RefExternalSchool, TeacherParticularMission,
    RefParticularMission, SystemSetting, Service, ServiceRepartition, RefGrade,
)
from backend.app.models.mef import MefService
from backend.app.models.trmd_synthesis import TrmdLine

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


def _base_setup(db, code="MATH"):
    school = School.create(db, {"uai": "1234567A", "name": "Collège Test"})
    discipline = Discipline.create(db, {"code": code, "name": f"Discipline {code}"})
    subject = Subject.create(db, {"code": code, "code_nomenclature": f"N_{code}", "short_name": code, "name": code, "discipline_id": discipline.id})
    ref_grade = RefGrade.create(db, {"name": f"NIVEAU_{code}"})
    mef = Mef.create(db, {"school_id": school.id, "code_national": "10010012110", "name": "6EME", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 60})
    division = Division.create(db, {"school_id": school.id, "code": "6A", "name": "6ème A"})
    mef_division = MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 28})
    mef_service = MefService.create(db, {"mef_id": mef.id, "subject_id": subject.id, "discipline_id": discipline.id})
    service = db.query(Service).filter(Service.mef_service_id == mef_service.id, Service.mef_division_id == mef_division.id).one()
    return school, discipline, subject, mef, division, mef_division, mef_service, service


def _make_teacher(db, school, code, discipline, discipline_minutes=1000, is_temporary_support=False):
    teacher = Teacher.create(db, {"code": code, "last_name": f"L{code}", "school_id": school.id, "is_temporary_support": is_temporary_support})
    TeacherDiscipline.create(db, {"teacher_id": teacher.id, "discipline_id": discipline.id, "duration_minutes": discipline_minutes})
    return teacher


class TestTrmdLineNeeds:
    def test_need_raw_and_weighted_sum_service_repartitions_of_the_discipline(self, db_session):
        school, discipline, subject, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        service.update(db_session, {"weighting_coefficient": 1.5, "weekly_duration_full_class_minutes": 120})

        lines = TrmdLine.read(db_session)
        line = next(l for l in lines if l.discipline_id == discipline.id)

        # FULL_CLASS 120min -> 1 ligne (60min x occurrence_count=2 x group_count=1) = raw 120
        assert line.need_raw_duration_minutes == 120
        assert line.need_weighted_duration_minutes == 180  # 120 x 1.5
        assert set(line.need_ids) == {r.id for r in service.repartitions}

    def test_shared_reduced_repartition_counted_once_across_two_services(self, db_session):
        school, discipline, subject, mef, division, mef_division, mef_service, s1 = _base_setup(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})
        s2 = db_session.query(Service).filter(Service.mef_service_id == mef_service.id, Service.mef_division_id == mef_division_b.id).one()
        mef_service.update(db_session, {"reduced_group_student_count": 10})
        from backend.app.models.service import Alignment
        alignment = Alignment.create(db_session, {"code": "AL_TRMD", "name": "Alignement TRMD"})
        s1.update(db_session, {"alignment_id": alignment.id, "student_count": 12})
        s2.update(db_session, {"alignment_id": alignment.id, "student_count": 13})
        s1.update(db_session, {"weekly_duration_reduced_minutes": 60})
        s2.update(db_session, {"weekly_duration_reduced_minutes": 60})

        lines = TrmdLine.read(db_session)
        line = next(l for l in lines if l.discipline_id == discipline.id)

        r1 = next(r for r in s1.repartitions if r.group_type.value == "REDUCED")
        r2 = next(r for r in s2.repartitions if r.group_type.value == "REDUCED")
        # dédupliqué : une seule des deux lignes REDUCED partagées compte dans need_ids/need_raw
        assert (r1.id in line.need_ids) != (r2.id in line.need_ids)
        assert line.need_raw_duration_minutes == min(r1.raw_need_weekly_duration_minutes, r2.raw_need_weekly_duration_minutes)


class TestTrmdLineResources:
    def test_def_and_temp_teachers_split_and_summed_separately(self, db_session):
        school, discipline, subject, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        def_teacher = _make_teacher(db_session, school, "DEF1", discipline, discipline_minutes=1080)
        temp_teacher = _make_teacher(db_session, school, "TMP1", discipline, discipline_minutes=600, is_temporary_support=True)

        lines = TrmdLine.read(db_session)
        line = next(l for l in lines if l.discipline_id == discipline.id)

        assert line.def_teacher_ids == [def_teacher.id]
        assert line.temp_teacher_ids == [temp_teacher.id]
        assert line.def_teacher_count == 1
        assert line.temp_teacher_count == 1
        assert line.def_teached_duration_minutes == 1080
        assert line.temp_teached_duration_minutes == 600

    def test_ara_is_subtracted_from_teached_duration(self, db_session):
        school, discipline, subject, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=1080)
        ref_ara = RefAra.create(db_session, {"name": "ARA Test"})
        TeacherAra.create(db_session, {"teacher_id": teacher.id, "ref_ara_id": ref_ara.id, "duration_minutes": 120})

        lines = TrmdLine.read(db_session)
        line = next(l for l in lines if l.discipline_id == discipline.id)

        assert line.def_teached_duration_minutes == 1080 - 120

    def test_other_school_counted_for_def_and_temp_teachers_alike(self, db_session):
        school, discipline, subject, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        def_teacher = _make_teacher(db_session, school, "DEF2", discipline)
        temp_teacher = _make_teacher(db_session, school, "TMP2", discipline, is_temporary_support=True)
        ref_school = RefExternalSchool.create(db_session, {"name": "Collège Voisin"})
        TeacherOtherSchool.create(db_session, {"teacher_id": def_teacher.id, "ref_external_school_id": ref_school.id, "duration_minutes": 60})
        TeacherOtherSchool.create(db_session, {"teacher_id": temp_teacher.id, "ref_external_school_id": ref_school.id, "duration_minutes": 30})

        lines = TrmdLine.read(db_session)
        line = next(l for l in lines if l.discipline_id == discipline.id)

        assert line.def_given_duration_minutes == 60
        assert line.temp_given_duration_minutes == 30

    def test_imp_reads_particular_mission_lines(self, db_session):
        school, discipline, subject, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        teacher = _make_teacher(db_session, school, "T2", discipline)
        ref_mission = RefParticularMission.create(db_session, {"name": "Mission Test"})
        TeacherParticularMission.create(db_session, {"teacher_id": teacher.id, "ref_particular_mission_id": ref_mission.id, "duration_minutes": 45})

        lines = TrmdLine.read(db_session)
        line = next(l for l in lines if l.discipline_id == discipline.id)

        assert line.imp_duration_minutes == 45


class TestTrmdLineTotals:
    def test_gap_and_hsa_are_mutually_exclusive_and_never_negative(self, db_session):
        school, discipline, subject, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        service.update(db_session, {"weekly_duration_full_class_minutes": 60})  # besoin = 60
        _make_teacher(db_session, school, "T3", discipline, discipline_minutes=600)  # ressource = 600

        lines = TrmdLine.read(db_session)
        line = next(l for l in lines if l.discipline_id == discipline.id)

        assert line.total_needs == 60
        assert line.total_ressource_duration_minutes == 600
        assert line.total_gap_duration_minutes == 540
        assert line.total_hsa_duration_minutes == 0

    def test_hsa_when_needs_exceed_resources(self, db_session):
        school, discipline, subject, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        service.update(db_session, {"weekly_duration_full_class_minutes": 600})
        _make_teacher(db_session, school, "T4", discipline, discipline_minutes=60)

        lines = TrmdLine.read(db_session)
        line = next(l for l in lines if l.discipline_id == discipline.id)

        assert line.total_gap_duration_minutes == 0
        assert line.total_hsa_duration_minutes > 0

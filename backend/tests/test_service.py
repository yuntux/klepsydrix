"""
Tests pour le modèle Service / ServiceRepartition / Alignment et leur articulation
avec MefService (gabarit réglementaire) et Course (entité plaçable).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Discipline, Subject, Mef, MefDivision, Division, ElectionMethod,
    Group, Service, ServiceRepartition, Alignment, Course, SystemSetting
)
from backend.app.models.service import RepartitionPeriodicity
from backend.app.core.time_utils import minutes_to_hours

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


class TestMinutesToHours:
    def test_whole_hour(self):
        assert minutes_to_hours(60) == (1.0, "1h")

    def test_half_hour(self):
        assert minutes_to_hours(30) == (0.5, "0h30")

    def test_hour_and_a_half(self):
        assert minutes_to_hours(90) == (1.5, "1h30")

    def test_zero(self):
        assert minutes_to_hours(0) == (0.0, "0h")

    def test_ten_hours_or_more_is_not_padded(self):
        assert minutes_to_hours(600) == (10.0, "10h")
        assert minutes_to_hours(630) == (10.5, "10h30")


def _base_fixtures(db):
    school = School.create(db, {"uai": "1234567A", "name": "Collège Test"})
    discipline = Discipline.create(db, {"code": "GEN", "name": "Général"})
    subject = Subject.create(db, {"code": "MATH", "code_nomenclature": "N_MATH", "short_name": "Maths", "name": "Mathématiques", "discipline_id": discipline.id})
    mef = Mef.create(db, {"school_id": school.id, "code_national": "10010012110", "name": "6EME", "max_students_per_class": 30, "forecast_student_count": 60})
    division = Division.create(db, {"school_id": school.id, "code": "6A", "name": "6ème A"})
    mef_division = MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 28})
    return school, discipline, subject, mef, division, mef_division


class TestMefServiceFields:
    def test_total_weekly_duration_is_sum_of_three(self, db_session):
        _, _, subject, mef, _, _ = _base_fixtures(db_session)
        from backend.app.models.mef import MefService
        ms = MefService.create(db_session, {
            "mef_id": mef.id,
            "subject_id": subject.id,
            "weekly_duration_full_class_minutes": 120,
            "weekly_duration_reduced_minutes": 30,
            "weekly_duration_split_minutes": 30,
        })
        assert ms.total_weekly_duration_minutes == 180


class TestServiceStructure:
    def test_service_requires_exactly_one_structure(self, db_session):
        _, _, subject, mef, division, mef_division = _base_fixtures(db_session)

        with pytest.raises(ValueError, match="doit être rattaché"):
            Service.create(db_session, {
                "subject_id": subject.id,
                "student_count": 28,
            })

    def test_service_rejects_both_structures(self, db_session):
        _, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        group = Group.create(db_session, {"code": "GRP1", "name": "Groupe 1"})

        with pytest.raises(ValueError, match="ne peut pas être rattaché"):
            Service.create(db_session, {
                "subject_id": subject.id,
                "mef_division_id": mef_division.id,
                "group_id": group.id,
            })

    def test_service_division_id_derived_from_mef_division(self, db_session):
        _, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        service = Service.create(db_session, {
            "subject_id": subject.id,
            "mef_division_id": mef_division.id,
        })
        assert service.division_id == division.id

    def test_service_rejects_mismatched_mef(self, db_session):
        school, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        from backend.app.models.mef import MefService
        other_mef = Mef.create(db_session, {"school_id": school.id, "code_national": "10010012199", "name": "5EME", "max_students_per_class": 30, "forecast_student_count": 30})
        other_mef_service = MefService.create(db_session, {"mef_id": other_mef.id, "subject_id": subject.id})

        with pytest.raises(ValueError, match="même MEF"):
            Service.create(db_session, {
                "subject_id": subject.id,
                "mef_division_id": mef_division.id,
                "mef_service_id": other_mef_service.id,
            })


class TestServiceSyncIndicator:
    def test_ad_hoc_service_is_always_synced(self, db_session):
        _, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        service = Service.create(db_session, {
            "subject_id": subject.id,
            "mef_division_id": mef_division.id,
        })
        assert service.is_synced_with_mef_service is True

    def test_service_generated_from_template_is_synced_until_diverging(self, db_session):
        _, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        from backend.app.models.mef import MefService
        mef_service = MefService.create(db_session, {
            "mef_id": mef.id,
            "subject_id": subject.id,
            "weekly_duration_full_class_minutes": 120,
            "weekly_duration_reduced_minutes": 0,
            "weekly_duration_split_minutes": 30,
            "weighting_coefficient": 1.0,
        })
        # mef_division existe déjà (via _base_fixtures) : la création du MefService a donc
        # déjà généré automatiquement le Service correspondant (voir MefService.create()).
        service = db_session.query(Service).filter(
            Service.mef_service_id == mef_service.id,
            Service.mef_division_id == mef_division.id,
        ).one()
        assert service.is_synced_with_mef_service is True

        service.update(db_session, {"weighting_coefficient": 1.1})
        assert service.is_synced_with_mef_service is False

        # Modifier le gabarit ne resynchronise pas automatiquement le service (propagation à sens unique)
        mef_service.update(db_session, {"weekly_duration_full_class_minutes": 150})
        assert service.weekly_duration_full_class_minutes == 120


class TestServiceRepartition:
    def test_duration_must_be_multiple_of_timeslot(self, db_session):
        _, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        service = Service.create(db_session, {"subject_id": subject.id, "mef_division_id": mef_division.id})

        with pytest.raises(ValueError, match="multiple exact"):
            ServiceRepartition.create(db_session, {
                "service_id": service.id,
                "occurrence_count": 1,
                "duration_minutes": 45,
                "periodicity": "WEEKLY",
            })

    def test_valid_repartition_created(self, db_session):
        _, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        service = Service.create(db_session, {"subject_id": subject.id, "mef_division_id": mef_division.id})

        r1 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        r2 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "BIWEEKLY"})
        assert r1.id is not None and r2.id is not None
        assert len(service.repartitions) == 2

    def test_name_is_computed_and_stored_on_create(self, db_session):
        _, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        service = Service.create(db_session, {"subject_id": subject.id, "mef_division_id": mef_division.id})

        r_weekly = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        assert r_weekly.name == "2x1h(H)"

        r_biweekly = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 90, "periodicity": "BIWEEKLY"})
        assert r_biweekly.name == "1x1h30(Q)"

    def test_name_is_recomputed_on_update(self, db_session):
        _, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        service = Service.create(db_session, {"subject_id": subject.id, "mef_division_id": mef_division.id})
        r = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})
        assert r.name == "1x1h(H)"

        r.update(db_session, {"occurrence_count": 3, "duration_minutes": 30})
        assert r.name == "3x0h30(H)"


class TestAlignment:
    def _make_service(self, db, subject, mef_division, **overrides):
        vals = {"subject_id": subject.id, "mef_division_id": mef_division.id}
        vals.update(overrides)
        return Service.create(db, vals)

    def test_services_with_matching_repartition_can_align(self, db_session):
        school, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})

        alignment = Alignment.create(db_session, {"code": "AL1", "name": "Alignement Test"})
        s1 = self._make_service(db_session, subject, mef_division)
        s2 = self._make_service(db_session, subject, mef_division_b)

        ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})

        s1.update(db_session, {"alignment_id": alignment.id})
        s2.update(db_session, {"alignment_id": alignment.id})
        assert s2.alignment_id == alignment.id

    def test_services_with_mismatched_repartition_cannot_align(self, db_session):
        school, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})

        alignment = Alignment.create(db_session, {"code": "AL2", "name": "Alignement Test 2"})
        s1 = self._make_service(db_session, subject, mef_division)
        s2 = self._make_service(db_session, subject, mef_division_b)

        ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})

        s1.update(db_session, {"alignment_id": alignment.id})
        with pytest.raises(ValueError, match="même modèle de répartition"):
            s2.update(db_session, {"alignment_id": alignment.id})

    def test_editing_repartition_after_alignment_is_blocked_if_it_breaks_homogeneity(self, db_session):
        school, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})

        alignment = Alignment.create(db_session, {"code": "AL3", "name": "Alignement Test 3"})
        s1 = self._make_service(db_session, subject, mef_division)
        s2 = self._make_service(db_session, subject, mef_division_b)

        r1 = ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        s1.update(db_session, {"alignment_id": alignment.id})
        s2.update(db_session, {"alignment_id": alignment.id})

        with pytest.raises(ValueError, match="homogénéité"):
            r1.update(db_session, {"occurrence_count": 3})


class TestCourseServiceConsistency:
    def test_leaf_course_without_service_is_consistent(self, db_session):
        school, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        course = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 60})
        assert course.is_consistent_with_service is True

    def test_leaf_course_matching_repartition_is_consistent(self, db_session):
        school, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        service = Service.create(db_session, {"subject_id": subject.id, "mef_division_id": mef_division.id})
        repartition = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})

        course = Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "duration_minutes": 60,
            "week_type": "W", "service_repartition_id": repartition.id,
        })
        assert course.is_consistent_with_service is True

    def test_leaf_course_diverging_duration_is_inconsistent(self, db_session):
        school, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        service = Service.create(db_session, {"subject_id": subject.id, "mef_division_id": mef_division.id})
        repartition = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})

        course = Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "duration_minutes": 90,
            "week_type": "W", "service_repartition_id": repartition.id,
        })
        assert course.is_consistent_with_service is False

    def test_composed_course_with_children_is_always_consistent(self, db_session):
        school, _, subject, mef, division, mef_division = _base_fixtures(db_session)
        service = Service.create(db_session, {"subject_id": subject.id, "mef_division_id": mef_division.id})
        repartition = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})

        parent = Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "duration_minutes": 90,
            "is_composed": True, "service_repartition_id": repartition.id,
        })
        Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 60, "parent_id": parent.id})
        assert parent.is_consistent_with_service is True

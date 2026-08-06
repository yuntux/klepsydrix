"""
Tests pour le modèle Service / ServiceRepartition / Alignment et leur articulation
avec MefService (gabarit réglementaire) et Course (entité plaçable).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
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
    """
    Fixtures communes. mef_division existe déjà avant la création de mef_service : la création de
    ce dernier déclenche donc automatiquement la génération d'un Service pour ce couple (voir
    MefService.create()) — service est ce Service auto-généré, prêt à l'emploi pour tout test qui
    n'a pas besoin de contrôler lui-même les valeurs du gabarit.
    """
    school = School.create(db, {"uai": "1234567A", "name": "Collège Test"})
    discipline = Discipline.create(db, {"code": "GEN", "name": "Général"})
    subject = Subject.create(db, {"code": "MATH", "code_nomenclature": "N_MATH", "short_name": "Maths", "name": "Mathématiques", "discipline_id": discipline.id})
    mef = Mef.create(db, {"school_id": school.id, "code_national": "10010012110", "name": "6EME", "max_students_per_class": 30, "forecast_student_count": 60})
    division = Division.create(db, {"school_id": school.id, "code": "6A", "name": "6ème A"})
    mef_division = MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 28})
    from backend.app.models.mef import MefService
    mef_service = MefService.create(db, {"mef_id": mef.id, "subject_id": subject.id})
    service = db.query(Service).filter(
        Service.mef_service_id == mef_service.id,
        Service.mef_division_id == mef_division.id,
    ).one()
    return school, discipline, subject, mef, division, mef_division, mef_service, service


class TestMefServiceFields:
    def test_total_weekly_duration_is_sum_of_three(self, db_session):
        _, _, subject, mef, _, _, _, _ = _base_fixtures(db_session)
        from backend.app.models.mef import MefService
        ms = MefService.create(db_session, {
            "mef_id": mef.id,
            "subject_id": subject.id,
            "weekly_duration_full_class_minutes": 120,
            "weekly_duration_reduced_minutes": 30,
            "weekly_duration_split_minutes": 30,
        })
        assert ms.total_weekly_duration_minutes == 180

    def test_deleting_mef_service_deletes_its_generated_services(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        repartition = ServiceRepartition.create(db_session, {
            "service_id": service.id, "occurrence_count": 1, "duration_minutes": 30, "periodicity": "WEEKLY",
        })

        mef_service.delete(db_session)

        assert db_session.query(Service).filter(Service.id == service.id).first() is None
        assert db_session.query(ServiceRepartition).filter(ServiceRepartition.id == repartition.id).first() is None

    def test_deleting_mef_service_does_not_touch_unrelated_services(self, db_session):
        school, discipline, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        subject_b = Subject.create(db_session, {"code": "FR", "code_nomenclature": "N_FR", "short_name": "Français", "name": "Français", "discipline_id": discipline.id})
        from backend.app.models.mef import MefService
        other_mef_service = MefService.create(db_session, {"mef_id": mef.id, "subject_id": subject_b.id})
        other_service = db_session.query(Service).filter(Service.mef_service_id == other_mef_service.id).one()

        mef_service.delete(db_session)

        assert db_session.query(Service).filter(Service.id == other_service.id).first() is not None


class TestMefDivisionDeletion:
    """
    Service.mef_division_id porte ondelete="SET NULL" (contrairement à mef_service_id, qui est
    en CASCADE) : un Service peut légitimement survivre sans MefDivision s'il est rattaché à un
    Group à la place. Mais un Service généré via MefDivision n'a pas de group_id — le nullifier
    violerait donc _check_structure_exclusivity. Grâce à CRUDMixin._cascade_delete_dependents()
    (base.py), ce nullify passe désormais par un vrai Service.update(), qui revalide réellement
    la contrainte et bloque la suppression au lieu de la laisser corrompre les données en
    silence (c'était le risque précédemment identifié et non traité pour MefDivision -> Service).
    """
    def test_deleting_mef_division_is_blocked_if_a_service_would_be_left_without_structure(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        # Commit explicite : le rollback déclenché par l'échec ci-dessous revient à ce point (et
        # non au tout début de la session, qui ne committe jamais rien par défaut dans ce fixture).
        db_session.commit()

        with pytest.raises(ValueError, match="doit être rattaché"):
            mef_division.delete(db_session)

        # Le rollback a déjà eu lieu à l'intérieur de Service.update() (voir CRUDMixin) : ni le
        # Service, ni le MefDivision n'ont été supprimés.
        assert db_session.query(MefDivision).filter(MefDivision.id == mef_division.id).first() is not None
        assert db_session.query(Service).filter(Service.id == service.id).first() is not None

    def test_deleting_mef_division_succeeds_once_no_service_references_it(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        service.delete(db_session)

        mef_division.delete(db_session)

        assert db_session.query(MefDivision).filter(MefDivision.id == mef_division.id).first() is None


class TestServiceStructure:
    def test_service_requires_mef_service_id(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        with pytest.raises(IntegrityError):
            Service.create(db_session, {
                "subject_id": subject.id,
                "mef_division_id": mef_division.id,
            })

    def test_service_requires_exactly_one_structure(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)

        with pytest.raises(ValueError, match="doit être rattaché"):
            Service.create(db_session, {
                "subject_id": subject.id,
                "mef_service_id": mef_service.id,
                "student_count": 28,
            })

    def test_service_rejects_both_structures(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        group = Group.create(db_session, {"name": "Groupe 1"})

        with pytest.raises(ValueError, match="ne peut pas être rattaché"):
            Service.create(db_session, {
                "subject_id": subject.id,
                "mef_service_id": mef_service.id,
                "mef_division_id": mef_division.id,
                "group_id": group.id,
            })

    def test_service_division_id_derived_from_mef_division(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        assert service.division_id == division.id

    def test_service_rejects_mismatched_mef(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
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
    def test_service_generated_from_template_is_synced_until_diverging(self, db_session):
        _, _, subject, mef, division, mef_division, _, _ = _base_fixtures(db_session)
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

        # Modifier le gabarit réécrase les champs miroirs de TOUS ses services (y compris déjà
        # divergés) : le service perd son ajustement local (weighting_coefficient revient à 1.0,
        # la valeur du gabarit) et repasse synchronisé.
        mef_service.update(db_session, {"weekly_duration_full_class_minutes": 150})
        assert service.weekly_duration_full_class_minutes == 150
        assert service.weighting_coefficient == 1.0
        assert service.is_synced_with_mef_service is True

    def test_updating_mef_service_does_not_propagate_student_count(self, db_session):
        _, _, subject, mef, division, mef_division, _, _ = _base_fixtures(db_session)
        from backend.app.models.mef import MefService
        mef_service = MefService.create(db_session, {
            "mef_id": mef.id,
            "subject_id": subject.id,
            "student_count": 28,
        })
        service = db_session.query(Service).filter(Service.mef_service_id == mef_service.id).one()
        service.update(db_session, {"student_count": 15})

        mef_service.update(db_session, {"student_count": 30})
        assert service.student_count == 15

    def test_updating_mef_service_never_propagates_back_from_service_edits(self, db_session):
        _, _, subject, mef, division, mef_division, _, _ = _base_fixtures(db_session)
        from backend.app.models.mef import MefService
        mef_service = MefService.create(db_session, {
            "mef_id": mef.id,
            "subject_id": subject.id,
            "weekly_duration_full_class_minutes": 120,
        })
        service = db_session.query(Service).filter(Service.mef_service_id == mef_service.id).one()

        service.update(db_session, {"weekly_duration_full_class_minutes": 999})
        assert mef_service.weekly_duration_full_class_minutes == 120


class TestServiceRepartition:
    def test_duration_must_be_multiple_of_timeslot(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)

        with pytest.raises(ValueError, match="multiple exact"):
            ServiceRepartition.create(db_session, {
                "service_id": service.id,
                "occurrence_count": 1,
                "duration_minutes": 45,
                "periodicity": "WEEKLY",
            })

    def test_valid_repartition_created(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)

        r1 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        r2 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "BIWEEKLY"})
        assert r1.id is not None and r2.id is not None
        assert len(service.repartitions) == 2

    def test_name_is_computed_and_stored_on_create(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)

        r_weekly = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        assert r_weekly.name == "2x1h(H)"

        r_biweekly = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 90, "periodicity": "BIWEEKLY"})
        assert r_biweekly.name == "1x1h30(Q)"

    def test_name_is_recomputed_on_update(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        r = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})
        assert r.name == "1x1h(H)"

        r.update(db_session, {"occurrence_count": 3, "duration_minutes": 30})
        assert r.name == "3x0h30(H)"


class TestAlignment:
    def test_services_with_matching_repartition_can_align(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, s1 = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        # mef_service existe déjà : lier une nouvelle Division au MEF génère automatiquement son
        # propre Service pour ce même gabarit (voir MefDivision.create()).
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})
        s2 = db_session.query(Service).filter(
            Service.mef_service_id == mef_service.id,
            Service.mef_division_id == mef_division_b.id,
        ).one()

        alignment = Alignment.create(db_session, {"code": "AL1", "name": "Alignement Test"})
        ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})

        s1.update(db_session, {"alignment_id": alignment.id})
        s2.update(db_session, {"alignment_id": alignment.id})
        assert s2.alignment_id == alignment.id

    def test_services_with_mismatched_repartition_cannot_align(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, s1 = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})
        s2 = db_session.query(Service).filter(
            Service.mef_service_id == mef_service.id,
            Service.mef_division_id == mef_division_b.id,
        ).one()

        alignment = Alignment.create(db_session, {"code": "AL2", "name": "Alignement Test 2"})
        ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})

        s1.update(db_session, {"alignment_id": alignment.id})
        with pytest.raises(ValueError, match="même modèle de répartition"):
            s2.update(db_session, {"alignment_id": alignment.id})

    def test_editing_repartition_of_aligned_service_propagates_to_siblings(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, s1 = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})
        s2 = db_session.query(Service).filter(
            Service.mef_service_id == mef_service.id,
            Service.mef_division_id == mef_division_b.id,
        ).one()

        alignment = Alignment.create(db_session, {"code": "AL3", "name": "Alignement Test 3"})
        r1 = ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        s1.update(db_session, {"alignment_id": alignment.id})
        s2.update(db_session, {"alignment_id": alignment.id})

        r1.update(db_session, {"occurrence_count": 3})

        db_session.refresh(s2)
        s2_repartitions = list(s2.repartitions)
        assert len(s2_repartitions) == 1
        assert s2_repartitions[0].occurrence_count == 3
        assert s2_repartitions[0].duration_minutes == 60

    def test_deleting_repartition_of_aligned_service_propagates_to_siblings(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, s1 = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})
        s2 = db_session.query(Service).filter(
            Service.mef_service_id == mef_service.id,
            Service.mef_division_id == mef_division_b.id,
        ).one()

        alignment = Alignment.create(db_session, {"code": "AL4", "name": "Alignement Test 4"})
        r1_a = ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        r1_b = ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 1, "duration_minutes": 30, "periodicity": "BIWEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 1, "duration_minutes": 30, "periodicity": "BIWEEKLY"})
        s1.update(db_session, {"alignment_id": alignment.id})
        s2.update(db_session, {"alignment_id": alignment.id})

        r1_b.delete(db_session)

        db_session.refresh(s2)
        s2_repartitions = list(s2.repartitions)
        assert len(s2_repartitions) == 1
        assert s2_repartitions[0].occurrence_count == 2
        assert s2_repartitions[0].duration_minutes == 60

    def test_editing_repartition_propagates_across_three_aligned_services(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, s1 = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        division_c = Division.create(db_session, {"school_id": school.id, "code": "6C", "name": "6ème C"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})
        mef_division_c = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_c.id})
        s2 = db_session.query(Service).filter(Service.mef_service_id == mef_service.id, Service.mef_division_id == mef_division_b.id).one()
        s3 = db_session.query(Service).filter(Service.mef_service_id == mef_service.id, Service.mef_division_id == mef_division_c.id).one()

        alignment = Alignment.create(db_session, {"code": "AL5", "name": "Alignement Test 5"})
        r1 = ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s3.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        s1.update(db_session, {"alignment_id": alignment.id})
        s2.update(db_session, {"alignment_id": alignment.id})
        s3.update(db_session, {"alignment_id": alignment.id})

        r1.update(db_session, {"duration_minutes": 30})

        db_session.refresh(s2)
        db_session.refresh(s3)
        assert [r.duration_minutes for r in s2.repartitions] == [30]
        assert [r.duration_minutes for r in s3.repartitions] == [30]

    def test_editing_repartition_of_unaligned_service_does_not_touch_others(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, s1 = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})
        s2 = db_session.query(Service).filter(
            Service.mef_service_id == mef_service.id,
            Service.mef_division_id == mef_division_b.id,
        ).one()

        r1 = ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        r2 = ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})

        r1.update(db_session, {"occurrence_count": 5})

        db_session.refresh(s2)
        assert [r.occurrence_count for r in s2.repartitions] == [2]


class TestCourseServiceConsistency:
    def test_leaf_course_without_service_is_consistent(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        course = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 60})
        assert course.is_consistent_with_service is True

    def test_leaf_course_matching_repartition_is_consistent(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        repartition = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})

        course = Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "duration_minutes": 60,
            "week_type": "W", "service_repartition_id": repartition.id,
        })
        assert course.is_consistent_with_service is True

    def test_leaf_course_diverging_duration_is_inconsistent(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        repartition = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})

        course = Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "duration_minutes": 90,
            "week_type": "W", "service_repartition_id": repartition.id,
        })
        assert course.is_consistent_with_service is False

    def test_composed_course_with_children_is_always_consistent(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        repartition = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})

        parent = Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "duration_minutes": 90,
            "is_composed": True, "service_repartition_id": repartition.id,
        })
        Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 60, "parent_id": parent.id})
        assert parent.is_consistent_with_service is True

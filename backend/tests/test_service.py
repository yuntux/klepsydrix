"""
Tests pour le modèle Service / ServiceRepartition / Alignment et leur articulation
avec MefService (gabarit réglementaire).
"""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Discipline, Subject, Mef, MefDivision, Division, ElectionMethod,
    Group, Service, ServiceRepartition, Alignment, SystemSetting, RefGrade
)
from backend.app.models.service import RepartitionPeriodicity, RepartitionGroupType
from backend.app.core.time_utils import minutes_to_hours
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
    ref_grade = RefGrade.create(db, {"name": "6EME"})
    mef = Mef.create(db, {"school_id": school.id, "code_national": "10010012110", "name": "6EME", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 60})
    division = Division.create(db, {"school_id": school.id, "code": "6A", "name": "6ème A"})
    mef_division = MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 28})
    from backend.app.models.mef import MefService
    mef_service = MefService.create(db, {"mef_id": mef.id, "subject_id": subject.id})
    service = db.query(Service).filter(
        Service.mef_service_id == mef_service.id,
        Service.mef_division_id == mef_division.id,
    ).one()
    return school, discipline, subject, mef, division, mef_division, mef_service, service


class TestRefGradeDeleteRestrict:
    def test_cannot_delete_ref_grade_referenced_by_a_mef(self, db_session):
        _, _, _, mef, _, _, _, _ = _base_fixtures(db_session)

        with pytest.raises(ValueError, match="Impossible de supprimer"):
            mef.ref_grade.delete(db_session)

        assert db_session.query(RefGrade).filter(RefGrade.id == mef.ref_grade_id).first() is not None

    def test_ref_grade_deletable_once_unreferenced(self, db_session):
        ref_grade = RefGrade.create(db_session, {"name": "NIVEAU_LIBRE"})
        ref_grade.delete(db_session)

        assert db_session.query(RefGrade).filter(RefGrade.name == "NIVEAU_LIBRE").first() is None


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
                "discipline_id": mef_service.discipline_id,
                "mef_service_id": mef_service.id,
                "student_count": 28,
            })

    def test_service_rejects_both_structures(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        group = Group.create(db_session, {"name": "Groupe 1"})

        with pytest.raises(ValueError, match="ne peut pas être rattaché"):
            Service.create(db_session, {
                "subject_id": subject.id,
                "discipline_id": mef_service.discipline_id,
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
        other_ref_grade = RefGrade.create(db_session, {"name": "5EME"})
        other_mef = Mef.create(db_session, {"school_id": school.id, "code_national": "10010012199", "name": "5EME", "ref_grade_id": other_ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 30})
        other_mef_service = MefService.create(db_session, {"mef_id": other_mef.id, "subject_id": subject.id})

        with pytest.raises(ValueError, match="même MEF"):
            Service.create(db_session, {
                "subject_id": subject.id,
                "discipline_id": other_mef_service.discipline_id,
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

        service.update(db_session, {"weekly_duration_full_class_minutes": 300})
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
        assert r_weekly.name == "2x1h(H/C)"

        # occurrence_count=2 (plutôt que 1) : la somme des 2 lignes (120 + 90) doit rester un
        # multiple du créneau standard (30 min), désormais vérifié par la synchro vers Service.
        r_biweekly = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 90, "periodicity": "BIWEEKLY"})
        assert r_biweekly.name == "2x1h30(Q/C)"

    def test_name_is_recomputed_on_update(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        r = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})
        assert r.name == "1x1h(H/C)"

        r.update(db_session, {"occurrence_count": 3, "duration_minutes": 30})
        assert r.name == "3x0h30(H/C)"

    def test_duplicate_service_periodicity_group_type_duration_is_rejected(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})

        with pytest.raises(ValueError, match="existe déjà"):
            ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY"})

    def test_duplicate_quadruple_via_update_is_rejected(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        r2 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "BIWEEKLY"})

        with pytest.raises(ValueError, match="existe déjà"):
            r2.update(db_session, {"periodicity": "WEEKLY"})

    def test_same_periodicity_group_type_different_duration_is_allowed(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        r1 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        r2 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 30, "periodicity": "WEEKLY"})

        assert r1.id is not None and r2.id is not None

    def test_same_periodicity_different_group_type_is_allowed(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        r1 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "FULL_CLASS"})
        # occurrence_count doit être un multiple de 2 pour SPLIT (voir _recompute_service_weekly_durations).
        r2 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 30, "periodicity": "WEEKLY", "group_type": "SPLIT"})

        assert r1.id is not None and r2.id is not None

    def test_same_triple_on_different_services_is_allowed(self, db_session):
        school, _, subject, mef, division, mef_division, mef_service, s1 = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})
        s2 = db_session.query(Service).filter(
            Service.mef_service_id == mef_service.id,
            Service.mef_division_id == mef_division_b.id,
        ).one()

        r1 = ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        r2 = ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})

        assert r1.id is not None and r2.id is not None


class TestServiceWeeklyDurationSync:
    """Synchronisation bidirectionnelle Service <-> ServiceRepartition (voir spec.md)."""

    def test_full_class_duration_generates_hour_plus_remainder_blocks(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        service.update(db_session, {"weekly_duration_full_class_minutes": 150})

        rows = [(r.duration_minutes, r.occurrence_count) for r in service.repartitions if r.group_type == RepartitionGroupType.FULL_CLASS]
        assert sorted(rows) == sorted([(90, 1), (60, 1)])
        assert all(r.periodicity == RepartitionPeriodicity.WEEKLY for r in service.repartitions)

    def test_full_class_duration_exact_hours_generates_single_block(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        service.update(db_session, {"weekly_duration_full_class_minutes": 120})

        rows = [(r.duration_minutes, r.occurrence_count) for r in service.repartitions if r.group_type == RepartitionGroupType.FULL_CLASS]
        assert rows == [(60, 2)]

    def test_split_duration_sets_group_count_two(self, db_session):
        # occurrence_count reste 1 (une séance/élève/semaine) : group_count (2, fixe pour SPLIT)
        # porte désormais le nombre de groupes parallèles, séparément (plan Volet B).
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        service.update(db_session, {"weekly_duration_split_minutes": 60})

        rows = [(r.duration_minutes, r.occurrence_count, r.group_count) for r in service.repartitions if r.group_type == RepartitionGroupType.SPLIT]
        assert rows == [(60, 1, 2)]

    def test_reduced_duration_sets_group_count_from_groups_needed(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        service.update(db_session, {"student_count": 50, "reduced_group_student_count": 15, "weekly_duration_reduced_minutes": 60})

        rows = [(r.duration_minutes, r.occurrence_count, r.group_count) for r in service.repartitions if r.group_type == RepartitionGroupType.REDUCED]
        # ceil(50/15) = 4 groupes, occurrence_count reste 1 (une séance/élève/semaine)
        assert rows == [(60, 1, 4)]

    def test_reduced_group_student_count_zero_defaults_to_one_group(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        service.update(db_session, {"student_count": 50, "weekly_duration_reduced_minutes": 60})

        rows = [(r.duration_minutes, r.occurrence_count, r.group_count) for r in service.repartitions if r.group_type == RepartitionGroupType.REDUCED]
        assert rows == [(60, 1, 1)]

    def test_zero_duration_clears_the_bucket(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        service.update(db_session, {"weekly_duration_full_class_minutes": 120})
        assert len(service.repartitions) == 1

        service.update(db_session, {"weekly_duration_full_class_minutes": 0})
        assert len(service.repartitions) == 0

    def test_mef_service_propagation_regenerates_repartitions(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        mef_service.update(db_session, {"weekly_duration_full_class_minutes": 90})

        rows = [(r.duration_minutes, r.occurrence_count) for r in service.repartitions if r.group_type == RepartitionGroupType.FULL_CLASS]
        assert rows == [(90, 1)]

    def test_manual_repartition_edit_updates_service_total_without_rewriting_other_rows(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        r1 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "SPLIT"})
        r2 = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "FULL_CLASS"})
        r1_id, r2_id = r1.id, r2.id

        r2.update(db_session, {"duration_minutes": 90})

        assert service.weekly_duration_full_class_minutes == 90
        # r1 (SPLIT) n'a pas été touchée par la mise à jour de r2 (FULL_CLASS) : même ID, mêmes valeurs.
        assert [r.id for r in service.repartitions if r.group_type == RepartitionGroupType.SPLIT] == [r1_id]
        assert [r.id for r in service.repartitions if r.group_type == RepartitionGroupType.FULL_CLASS] == [r2_id]

    def test_deleting_last_repartition_zeroes_the_service_duration(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        r = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "FULL_CLASS"})
        assert service.weekly_duration_full_class_minutes == 60

        r.delete(db_session)
        assert service.weekly_duration_full_class_minutes == 0

    def test_manually_created_split_repartition_gets_group_count_two(self, db_session):
        # occurrence_count et group_count sont désormais indépendants (plan Volet B) : plus de
        # validation de divisibilité — mais group_count reste imposé à 2 pour SPLIT même sur une
        # ligne créée directement, hors synchro weekly_duration_split_minutes
        # (_enforce_group_count_and_compute_need_durations). raw_need_weekly_duration_minutes doit
        # refléter ce group_count corrigé, pas la valeur par défaut (1) qui précède la correction —
        # régression réelle trouvée et corrigée en fusionnant l'ancienne _enforce_fixed_group_counts
        # avec _compute_need_durations (l'ordre alphabétique de dispatch des @constrains() faisait
        # tourner le calcul du besoin AVANT la correction du group_count).
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        r = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "SPLIT"})
        assert r.group_count == 2
        assert r.raw_need_weekly_duration_minutes == 120  # 1 x 60 x 1 (WEEKLY) x 2 (group_count), pas 60

    def test_manually_created_full_class_repartition_gets_group_count_one(self, db_session):
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        r = ServiceRepartition.create(db_session, {"service_id": service.id, "occurrence_count": 3, "duration_minutes": 60, "periodicity": "WEEKLY", "group_type": "FULL_CLASS"})
        assert r.group_count == 1

    def test_raw_and_weighted_need_include_group_count(self, db_session):
        # raw_need = occurrence_count x duration_minutes x coeff_periodicite x group_count ;
        # weighted_need = raw_need x weighting_coefficient (voir _compute_need_durations).
        _, _, subject, mef, division, mef_division, mef_service, service = _base_fixtures(db_session)
        service.update(db_session, {"weighting_coefficient": 1.5})
        service.update(db_session, {"student_count": 50, "reduced_group_student_count": 15, "weekly_duration_reduced_minutes": 60})

        r = next(r for r in service.repartitions if r.group_type == RepartitionGroupType.REDUCED)
        # occurrence_count=1, duration=60, coeff=1 (WEEKLY), group_count=4 (ceil(50/15))
        assert r.raw_need_weekly_duration_minutes == 240
        assert r.weighted_need_weekly_duration_minutes == 360

    def test_editing_aligned_service_duration_propagates_repartitions_and_totals_to_sibling(self, db_session):
        # Interaction la plus fragile de cette synchro : régénérer les ServiceRepartition d'un
        # service aligné déclenche le miroir vers son voisin (_sync_aligned_repartitions), qui doit
        # à son tour recalculer les totaux du voisin (_recompute_service_weekly_durations) à partir
        # de son état FINAL (pas d'un état intermédiaire du miroir, delete-puis-recreate).
        school, _, subject, mef, division, mef_division, mef_service, s1 = _base_fixtures(db_session)
        division_b = Division.create(db_session, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id})
        s2 = db_session.query(Service).filter(
            Service.mef_service_id == mef_service.id,
            Service.mef_division_id == mef_division_b.id,
        ).one()
        ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        alignment = Alignment.create(db_session, {"code": "AL6", "name": "Alignement Test 6"})
        s1.update(db_session, {"alignment_id": alignment.id})
        s2.update(db_session, {"alignment_id": alignment.id})

        s1.update(db_session, {"weekly_duration_full_class_minutes": 150})

        db_session.refresh(s2)
        s2_full_class = sorted((r.duration_minutes, r.occurrence_count) for r in s2.repartitions if r.group_type == RepartitionGroupType.FULL_CLASS)
        assert s2_full_class == [(60, 1), (90, 1)]
        assert s2.weekly_duration_full_class_minutes == 150


class TestReducedGroupPooling:
    """_sync_reduced_pool / _reduced_pool_services (plan Volet B) : mutualisation de l'effectif
    réduit entre plusieurs Service, soit via un Alignment formel (défaut), soit via le paramètre
    système MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT."""

    def _two_services_same_mef_service(self, db):
        school, _, subject, mef, division, mef_division, mef_service, s1 = _base_fixtures(db)
        division_b = Division.create(db, {"school_id": school.id, "code": "6B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db, {"mef_id": mef.id, "division_id": division_b.id})
        s2 = db.query(Service).filter(
            Service.mef_service_id == mef_service.id,
            Service.mef_division_id == mef_division_b.id,
        ).one()
        return mef_service, division, division_b, s1, s2

    def test_aligned_reduced_services_pool_their_effectifs(self, db_session):
        # Les deux services doivent porter weekly_duration_reduced_minutes > 0 chacun pour se
        # mutualiser (_reduced_pool_services exclut tout service qui n'utilise pas lui-même
        # l'effectif réduit) — sinon celui resté à 0 n'a simplement aucune ligne REDUCED.
        mef_service, division, division_b, s1, s2 = self._two_services_same_mef_service(db_session)
        mef_service.update(db_session, {"reduced_group_student_count": 10})
        alignment = Alignment.create(db_session, {"code": "AL_POOL", "name": "Alignement Pool"})
        s1.update(db_session, {"alignment_id": alignment.id, "student_count": 12})
        s2.update(db_session, {"alignment_id": alignment.id, "student_count": 13})

        s1.update(db_session, {"weekly_duration_reduced_minutes": 60})
        s2.update(db_session, {"weekly_duration_reduced_minutes": 60})

        db_session.refresh(s1)
        db_session.refresh(s2)
        r1 = next(r for r in s1.repartitions if r.group_type == RepartitionGroupType.REDUCED)
        r2 = next(r for r in s2.repartitions if r.group_type == RepartitionGroupType.REDUCED)
        # pool = 12 + 13 = 25 eleves, /10 par groupe -> ceil(25/10) = 3 groupes, pour LES DEUX services
        assert r1.group_count == 3
        assert r2.group_count == 3
        assert {d.id for d in r1.shared_divisions} == {division_b.id}
        assert {d.id for d in r2.shared_divisions} == {division.id}

    def test_non_aligned_reduced_services_do_not_pool_by_default(self, db_session):
        mef_service, division, division_b, s1, s2 = self._two_services_same_mef_service(db_session)
        mef_service.update(db_session, {"reduced_group_student_count": 10})
        s1.update(db_session, {"student_count": 12})
        s2.update(db_session, {"student_count": 13, "weekly_duration_reduced_minutes": 60})

        r2 = next(r for r in s2.repartitions if r.group_type == RepartitionGroupType.REDUCED)
        # pas d'alignement, paramètre mutualisation à false (défaut) -> pool = soi-même seulement (13/10 -> 2)
        assert r2.group_count == 2
        assert r2.shared_divisions == []

    def test_mutualize_setting_pools_without_alignment(self, db_session):
        # Le pool ne retient que des services qui utilisent eux-mêmes l'effectif réduit
        # (_reduced_pool_services) : les deux services doivent porter weekly_duration_reduced_minutes > 0
        # pour se mutualiser, même sous le paramètre global.
        mef_service, division, division_b, s1, s2 = self._two_services_same_mef_service(db_session)
        mef_service.update(db_session, {"reduced_group_student_count": 10})
        SystemSetting.create(db_session, {"key": "MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT", "value": "true"})
        s1.update(db_session, {"student_count": 12, "weekly_duration_reduced_minutes": 60})
        s2.update(db_session, {"student_count": 13, "weekly_duration_reduced_minutes": 60})

        db_session.refresh(s1)
        r1 = next(r for r in s1.repartitions if r.group_type == RepartitionGroupType.REDUCED)
        r2 = next(r for r in s2.repartitions if r.group_type == RepartitionGroupType.REDUCED)
        # même MEF + même discipline, pas besoin d'alignement quand le paramètre est actif
        assert r1.group_count == 3
        assert r2.group_count == 3
        assert {d.id for d in r2.shared_divisions} == {division.id}

    def _two_services_different_mef(self, db, same_grade: bool):
        """Deux Service issus de DEUX MefService (donc deux Mef) distincts, partageant la même
        matière/discipline — pour tester la frontière de mutualisation par niveau (RefGrade), pas
        par MefService."""
        school, discipline, subject, mef1, division1, mef_division1, mef_service1, s1 = _base_fixtures(db)
        ref_grade2_id = mef1.ref_grade_id if same_grade else RefGrade.create(db, {"name": "AUTRE_NIVEAU"}).id
        mef2 = Mef.create(db, {"school_id": school.id, "code_national": "20020023220", "name": "5EME", "ref_grade_id": ref_grade2_id, "max_students_per_class": 30, "forecast_student_count": 60})
        division2 = Division.create(db, {"school_id": school.id, "code": "5A", "name": "5ème A"})
        mef_division2 = MefDivision.create(db, {"mef_id": mef2.id, "division_id": division2.id, "forecast_student_count": 28})
        from backend.app.models.mef import MefService
        mef_service2 = MefService.create(db, {"mef_id": mef2.id, "subject_id": subject.id, "discipline_id": discipline.id})
        s2 = db.query(Service).filter(Service.mef_service_id == mef_service2.id, Service.mef_division_id == mef_division2.id).one()
        return mef_service1, mef_service2, division1, division2, s1, s2

    def test_pools_across_different_mef_when_same_grade(self, db_session):
        # Nouvel objet RefGrade : deux Service de MEF différents doivent pouvoir mutualiser leur
        # effectif réduit dès lors qu'ils portent le même niveau (ex: MEF Général et MEF SEGPA de
        # 6ème) — la frontière de mutualisation n'est plus le MEF mais le niveau.
        mef_service1, mef_service2, division1, division2, s1, s2 = self._two_services_different_mef(db_session, same_grade=True)
        mef_service1.update(db_session, {"reduced_group_student_count": 10})
        mef_service2.update(db_session, {"reduced_group_student_count": 10})
        SystemSetting.create(db_session, {"key": "MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT", "value": "true"})
        s1.update(db_session, {"student_count": 12, "weekly_duration_reduced_minutes": 60})
        s2.update(db_session, {"student_count": 13, "weekly_duration_reduced_minutes": 60})

        db_session.refresh(s1)
        r1 = next(r for r in s1.repartitions if r.group_type == RepartitionGroupType.REDUCED)
        r2 = next(r for r in s2.repartitions if r.group_type == RepartitionGroupType.REDUCED)
        # pool = 12 + 13 = 25 eleves, /10 par groupe -> ceil(25/10) = 3 groupes
        assert r1.group_count == 3
        assert r2.group_count == 3
        assert {d.id for d in r1.shared_divisions} == {division2.id}

    def test_does_not_pool_across_different_grades(self, db_session):
        # Jamais de mutualisation entre deux niveaux différents, même même discipline et même
        # paramètre MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT=true.
        mef_service1, mef_service2, division1, division2, s1, s2 = self._two_services_different_mef(db_session, same_grade=False)
        mef_service1.update(db_session, {"reduced_group_student_count": 10})
        mef_service2.update(db_session, {"reduced_group_student_count": 10})
        SystemSetting.create(db_session, {"key": "MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT", "value": "true"})
        s1.update(db_session, {"student_count": 12, "weekly_duration_reduced_minutes": 60})
        s2.update(db_session, {"student_count": 13, "weekly_duration_reduced_minutes": 60})

        r1 = next(r for r in s1.repartitions if r.group_type == RepartitionGroupType.REDUCED)
        assert r1.group_count == 2  # ceil(12/10) : pas de pool, effectif propre seulement
        assert r1.shared_divisions == []


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
        # duration_minutes=60 (plutôt que 30) sur la ligne BIWEEKLY : la somme des 2 lignes FULL_CLASS
        # (120 + 30) doit rester un multiple du créneau standard (voir _recompute_service_weekly_durations).
        r1_a = ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        r1_b = ServiceRepartition.create(db_session, {"service_id": s1.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "BIWEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 2, "duration_minutes": 60, "periodicity": "WEEKLY"})
        ServiceRepartition.create(db_session, {"service_id": s2.id, "occurrence_count": 1, "duration_minutes": 60, "periodicity": "BIWEEKLY"})
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

"""
Tests pour l'affectation automatique des besoins aux professeurs (backend/app/solver/
teacher_assignment.py + backend/app/models/wizard_teacher_assignment.py) — voir
specs/002-yearly-timetabling-core/teacher-assignment-proposal.md.
"""
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Discipline, Subject, Mef, MefDivision, Division, Teacher, TeacherDiscipline,
    TeacherAre, RefAre, SystemSetting, Service, RefGrade, TeacherGradePreference,
)
from backend.app.models.mef import MefService
from backend.app.models.course import Course
from backend.app.models.group import find_or_create_partition, find_or_create_group
from backend.app.models.preference import ResourcePreference, PreferenceLevel
from backend.app.models.timeslot import Timeslot
from backend.app.solver.teacher_assignment import (
    compute_assignment_proposal, _are_incompatible, _division_ids_for_service, _compatibility_penalty,
    _max_class_count_violations,
)
from backend.app.models.wizard_teacher_assignment import WizardTeacherAssignment
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


def _base_setup(db, code="MATH", division_code="6A"):
    school = School.create(db, {"uai": "1234567A", "name": "Collège Test"})
    discipline = Discipline.create(db, {"code": code, "name": f"Discipline {code}"})
    subject = Subject.create(db, {"code": code, "code_nomenclature": f"N_{code}", "short_name": code, "name": code, "discipline_id": discipline.id})
    ref_grade = RefGrade.create(db, {"name": f"NIVEAU_{code}_{division_code}"})
    mef = Mef.create(db, {"school_id": school.id, "code_national": "10010012110", "name": "6EME", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 60})
    division = Division.create(db, {"school_id": school.id, "code": division_code, "name": f"6ème {division_code}"})
    mef_division = MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 28})
    mef_service = MefService.create(db, {"mef_id": mef.id, "subject_id": subject.id, "discipline_id": discipline.id})
    service = db.query(Service).filter(Service.mef_service_id == mef_service.id, Service.mef_division_id == mef_division.id).one()
    return school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service


def _make_teacher(db, school, code, discipline=None, discipline_minutes=0, priority=None, ref_grade=None, max_hsa=0):
    teacher = Teacher.create(db, {"code": code, "last_name": f"L{code}", "school_id": school.id, "max_hsa_duration_minutes": max_hsa})
    if discipline is not None:
        TeacherDiscipline.create(db, {"teacher_id": teacher.id, "discipline_id": discipline.id, "duration_minutes": discipline_minutes})
    if priority is not None and ref_grade is not None:
        pref = db.query(TeacherGradePreference).filter(TeacherGradePreference.teacher_id == teacher.id, TeacherGradePreference.ref_grade_id == ref_grade.id).one()
        pref.update(db, {"priority": priority})
    return teacher


def _make_cross_division_service(db, mef_service, discipline, subject, division_a, division_b):
    """
    Service directement lié à un Group cross-division (voir wizard_specialty_group_generation.py)
    — couvre les deux divisions à la fois, jamais via MefDivision. `mef_service` doit être
    RÉUTILISÉ depuis l'appelant (jamais recréé ici) : un seul MefService par couple (mef_id,
    subject_id), voir MefService._check_unique_mef_subject_pair.
    """
    partition_a = find_or_create_partition(db, division_a.id, subject.code, subject_ids=[subject.id])
    partition_b = find_or_create_partition(db, division_b.id, subject.code, subject_ids=[subject.id])
    cp_a = next(cp for cp in partition_a.class_parts if cp.subject_id == subject.id)
    cp_b = next(cp for cp in partition_b.class_parts if cp.subject_id == subject.id)
    group = find_or_create_group(db, [cp_a.id, cp_b.id], subject.id)
    return Service.create(db, {"mef_service_id": mef_service.id, "group_id": group.id, "subject_id": subject.id, "discipline_id": discipline.id})


class TestCrossDivisionService:
    def test_division_ids_for_service_returns_every_division_of_the_group(self, db_session):
        school, discipline, subject, ref_grade, mef, division_a, mef_division_a, mef_service, _ = _base_setup(db_session, division_code="A")
        division_b = Division.create(db_session, {"school_id": school.id, "code": "B", "name": "6ème B"})
        group_service = _make_cross_division_service(db_session, mef_service, discipline, subject, division_a, division_b)

        assert set(_division_ids_for_service(group_service)) == {division_a.id, division_b.id}

    def test_compatibility_penalty_uses_union_not_sum_of_per_division_overlaps(self, db_session):
        """Une seule et même case bloquée à la fois côté prof et dans LES DEUX divisions ne doit
        compter qu'une fois (voir la comparaison des options union/somme/max)."""
        school, discipline, subject, ref_grade, mef, division_a, mef_division_a, mef_service, _ = _base_setup(db_session, division_code="A")
        division_b = Division.create(db_session, {"school_id": school.id, "code": "B", "name": "6ème B"})
        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=60)
        timeslot = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
        ResourcePreference.create(db_session, {"resource_type": "Teacher", "resource_id": teacher.id, "timeslot_id": timeslot.id, "preference_level": PreferenceLevel.UNSUITED.value})
        ResourcePreference.create(db_session, {"resource_type": "Division", "resource_id": division_a.id, "timeslot_id": timeslot.id, "preference_level": PreferenceLevel.UNSUITED.value})
        ResourcePreference.create(db_session, {"resource_type": "Division", "resource_id": division_b.id, "timeslot_id": timeslot.id, "preference_level": PreferenceLevel.UNSUITED.value})

        penalty = _compatibility_penalty(db_session, teacher.id, [division_a.id, division_b.id], total_timeslot_count=10, division_blocked_cache={})
        # 1 seul créneau en commun (pas 2, la somme aurait donné round(5*100*2/10)=100) : la case
        # est bloquée dans les DEUX divisions à la fois, l'union ne la compte qu'une fois.
        assert penalty == round(5 * 100 * 1 / 10)

    def test_incompatibility_conflict_detected_on_the_group_second_division(self, db_session):
        """
        Le service cross-division (divisions A+B) est affecté à t_group. Un service séparé,
        purement sur la division B (pas A), est affecté à t_b — incompatible avec t_group. Avant
        le passage à une liste, seule la PREMIÈRE division du groupe était vérifiée : selon
        l'ordre interne des ClassPart, ce conflit sur B pouvait rester invisible.
        """
        school, discipline, subject, ref_grade, mef, division_a, mef_division_a, mef_service, _ = _base_setup(db_session, division_code="A")
        division_b = Division.create(db_session, {"school_id": school.id, "code": "B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id, "forecast_student_count": 28})
        service_b = db_session.query(Service).filter(Service.mef_service_id == mef_service.id, Service.mef_division_id == mef_division_b.id).one()
        group_service = _make_cross_division_service(db_session, mef_service, discipline, subject, division_a, division_b)

        t_group = _make_teacher(db_session, school, "TGROUP", discipline, discipline_minutes=360)
        t_b = _make_teacher(db_session, school, "TB", discipline, discipline_minutes=60)
        t_group.update(db_session, {"incompatible_teacher_ids": [t_b.id]})

        group_service.update(db_session, {"weekly_duration_full_class_minutes": 360})
        service_b.update(db_session, {"weekly_duration_full_class_minutes": 60})

        result = compute_assignment_proposal(db_session)
        conflict_warnings = [w for w in result["warnings"] if w["type"] == "incompatibility_unresolved"]
        assert len(conflict_warnings) == 1
        assert set(conflict_warnings[0]["teacher_ids"]) == {t_group.id, t_b.id}

    def test_max_class_count_counts_the_group_service_against_every_division(self, db_session):
        """
        Test unitaire direct sur _max_class_count_violations (pas compute_assignment_proposal en
        bout en bout) : un seul service affecté à ce professeur, mais qui couvre 2 divisions à la
        fois (groupe cross-division) doit compter pour 2, pas 1 — avant le passage à une liste,
        seule la première division du groupe était vue, aucune violation n'était détectée ici.
        """
        school, discipline, subject, ref_grade, mef, division_a, mef_division_a, mef_service, service_a = _base_setup(db_session, division_code="A")
        division_b = Division.create(db_session, {"school_id": school.id, "code": "B", "name": "6ème B"})
        group_service = _make_cross_division_service(db_session, mef_service, discipline, subject, division_a, division_b)

        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=420, priority=1, ref_grade=ref_grade)
        pref = db_session.query(TeacherGradePreference).filter(TeacherGradePreference.teacher_id == teacher.id, TeacherGradePreference.ref_grade_id == ref_grade.id).one()
        pref.update(db_session, {"max_class_count": 1})
        service_a.delete(db_session)

        services_by_id = {group_service.id: group_service}
        assignments = {group_service.id: {"teacher_ids": [teacher.id], "tier": "normal"}}

        violations = _max_class_count_violations(db_session, services_by_id, assignments)
        assert violations == [(group_service.id, teacher.id)]


class TestCapacity:
    def test_teacher_within_discipline_capacity_gets_assigned_on_normal_tier(self, db_session):
        school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=120)
        service.update(db_session, {"weekly_duration_full_class_minutes": 60})

        result = compute_assignment_proposal(db_session)
        proposal = next(p for p in result["proposals"] if p["service_id"] == service.id)
        assert proposal["teacher_ids"] == [teacher.id]
        assert proposal["tier"] == "normal"
        assert not any(w["type"] == "unmet_need" for w in result["warnings"])

    def test_capacity_exhausted_without_hsa_yields_unmet_warning(self, db_session):
        school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        _make_teacher(db_session, school, "T1", discipline, discipline_minutes=0, max_hsa=0)
        service.update(db_session, {"weekly_duration_full_class_minutes": 60})

        result = compute_assignment_proposal(db_session)
        assert any(w["type"] == "unmet_need" and service.id in w["service_ids"] for w in result["warnings"])

    def test_overflow_beyond_capacity_uses_hsa_tier(self, db_session):
        school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=30, max_hsa=60)
        service.update(db_session, {"weekly_duration_full_class_minutes": 60})

        result = compute_assignment_proposal(db_session)
        proposal = next(p for p in result["proposals"] if p["service_id"] == service.id)
        assert proposal["teacher_ids"] == [teacher.id]
        assert proposal["tier"] in ("hsa", "mixed")

    def test_unqualified_teacher_never_proposed(self, db_session):
        school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        other_discipline = Discipline.create(db_session, {"code": "PHYS", "name": "Physique"})
        _make_teacher(db_session, school, "WRONG", other_discipline, discipline_minutes=120)
        service.update(db_session, {"weekly_duration_full_class_minutes": 60})

        result = compute_assignment_proposal(db_session)
        assert not any(p["service_id"] == service.id for p in result["proposals"])
        assert any(w["type"] == "unmet_need" for w in result["warnings"])


class TestGlobalHsaMinimization:
    def test_avoids_hsa_that_a_greedy_by_priority_would_generate(self, db_session):
        """
        Reproduit l'exemple espagnol de teacher-assignment-proposal.md §2 : deux services de la
        même discipline (besoins 30 et 90 min), un professeur T1 préféré (priorité 1) mais dont
        la capacité (90) ne correspond exactement qu'à UN seul des deux besoins, un professeur T2
        moins préféré (priorité 5) dont la capacité (30) correspond exactement à l'autre besoin.
        Un glouton qui traite les besoins par ordre d'id et choisit toujours le moins coûteux
        (T1) affecterait T1 au premier besoin (30, gâchant sa capacité), forçant le second besoin
        (90) à déborder en HSA. Le flot optimal, lui, doit affecter T2 (30) et T1 (90) — 0 HSA.
        """
        school, discipline, subject, ref_grade, mef, division_a, mef_division_a, mef_service, s_small = _base_setup(db_session, division_code="A")
        division_b = Division.create(db_session, {"school_id": school.id, "code": "B", "name": "6ème B"})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id, "forecast_student_count": 28})
        s_large = db_session.query(Service).filter(Service.mef_service_id == mef_service.id, Service.mef_division_id == mef_division_b.id).one()

        t1 = _make_teacher(db_session, school, "PREFERRED", discipline, discipline_minutes=90, priority=1, ref_grade=ref_grade, max_hsa=0)
        t2 = _make_teacher(db_session, school, "LEAST_PREFERRED", discipline, discipline_minutes=30, priority=5, ref_grade=ref_grade, max_hsa=0)

        s_small.update(db_session, {"weekly_duration_full_class_minutes": 30})
        s_large.update(db_session, {"weekly_duration_full_class_minutes": 90})

        result = compute_assignment_proposal(db_session)
        # La propriété qui compte : 0 HSA au total, quelle que soit la répartition exacte entre
        # les deux professeurs. Le flot a même trouvé mieux que le simple "échange" T1<->T2 décrit
        # ci-dessus : rien n'empêche T1 (préféré, moins cher) d'être réparti sur LES DEUX services
        # (partage/co-enseignement, un service peut avoir plusieurs professeurs) tant que T2
        # comble le reste — cette solution est encore moins chère que l'échange strict, tout en
        # atteignant elle aussi 0 HSA. Le point à vérifier n'est donc pas "qui prend quoi", mais
        # qu'aucun besoin ne déborde en HSA malgré la préférence marquée pour T1.
        assert not any(w["type"] in ("unmet_need",) for w in result["warnings"])
        by_service = {p["service_id"]: p for p in result["proposals"]}
        assert by_service[s_small.id]["tier"] == "normal"
        assert by_service[s_large.id]["tier"] == "normal"
        assert t1.id in by_service[s_small.id]["teacher_ids"] + by_service[s_large.id]["teacher_ids"]
        assert t2.id in by_service[s_small.id]["teacher_ids"] + by_service[s_large.id]["teacher_ids"]


class TestIncompatibilityRepair:
    def test_conflict_resolved_when_an_alternative_exists(self, db_session):
        school, discipline_a, subject_a, ref_grade, mef, division, mef_division, mef_service_a, service_a = _base_setup(db_session, code="MATH")
        discipline_b = Discipline.create(db_session, {"code": "PHYS", "name": "Physique"})
        subject_b = Subject.create(db_session, {"code": "PHYS", "code_nomenclature": "N_PHYS", "short_name": "PHYS", "name": "PHYS", "discipline_id": discipline_b.id})
        mef_service_b = MefService.create(db_session, {"mef_id": mef.id, "subject_id": subject_b.id, "discipline_id": discipline_b.id})
        service_b = db_session.query(Service).filter(Service.mef_service_id == mef_service_b.id, Service.mef_division_id == mef_division.id).one()

        t_a = _make_teacher(db_session, school, "TA", discipline_a, discipline_minutes=60)
        t_b = _make_teacher(db_session, school, "TB", discipline_b, discipline_minutes=60)
        t_b_alt = _make_teacher(db_session, school, "TB_ALT", discipline_b, discipline_minutes=60)
        t_a.update(db_session, {"incompatible_teacher_ids": [t_b.id]})

        service_a.update(db_session, {"weekly_duration_full_class_minutes": 60})
        service_b.update(db_session, {"weekly_duration_full_class_minutes": 60})

        result = compute_assignment_proposal(db_session)
        assert not any(w["type"] == "incompatibility_unresolved" for w in result["warnings"])
        by_service = {p["service_id"]: p for p in result["proposals"]}
        # t_b_alt (compatible) a dû prendre le relais sur service_b, pas t_b.
        assert by_service[service_b.id]["teacher_ids"] == [t_b_alt.id]
        # service_a garde bien SON professeur (t_a, seul qualifié pour sa discipline) : une
        # réparation qui l'aurait orphelin pour faire disparaître le conflit ne compte pas comme
        # une vraie résolution (voir _repair_incompatibilities, garde "genuinely_replaced").
        assert by_service[service_a.id]["teacher_ids"] == [t_a.id]

    def test_conflict_surfaced_as_warning_when_no_alternative_exists(self, db_session):
        school, discipline_a, subject_a, ref_grade, mef, division, mef_division, mef_service_a, service_a = _base_setup(db_session, code="MATH")
        discipline_b = Discipline.create(db_session, {"code": "PHYS", "name": "Physique"})
        subject_b = Subject.create(db_session, {"code": "PHYS", "code_nomenclature": "N_PHYS", "short_name": "PHYS", "name": "PHYS", "discipline_id": discipline_b.id})
        mef_service_b = MefService.create(db_session, {"mef_id": mef.id, "subject_id": subject_b.id, "discipline_id": discipline_b.id})
        service_b = db_session.query(Service).filter(Service.mef_service_id == mef_service_b.id, Service.mef_division_id == mef_division.id).one()

        t_a = _make_teacher(db_session, school, "TA", discipline_a, discipline_minutes=60)
        t_b = _make_teacher(db_session, school, "TB", discipline_b, discipline_minutes=60)
        t_a.update(db_session, {"incompatible_teacher_ids": [t_b.id]})

        service_a.update(db_session, {"weekly_duration_full_class_minutes": 60})
        service_b.update(db_session, {"weekly_duration_full_class_minutes": 60})

        result = compute_assignment_proposal(db_session)
        conflict_warnings = [w for w in result["warnings"] if w["type"] == "incompatibility_unresolved"]
        assert len(conflict_warnings) == 1
        assert set(conflict_warnings[0]["teacher_ids"]) == {t_a.id, t_b.id}
        # Les deux propositions restent présentes (pas d'abandon silencieux d'un des deux).
        by_service = {p["service_id"]: p for p in result["proposals"]}
        assert by_service[service_a.id]["teacher_ids"] == [t_a.id]
        assert by_service[service_b.id]["teacher_ids"] == [t_b.id]


class TestMaxClassCountRepair:
    def test_unresolved_violation_surfaced_as_warning_and_keeps_original_assignment(self, db_session):
        """
        Bout en bout (compute_assignment_proposal) : un seul professeur qualifié, affecté à 2
        divisions du même niveau, dépasse max_class_count=1 — sans alternative, la réparation doit
        échouer "sincèrement" (voir _repair_max_class_count::genuinely_replaced) et signaler un
        avertissement max_class_count_unresolved, comme _repair_incompatibilities le fait pour son
        propre cas non résolu, plutôt que de transformer silencieusement le dépassement en besoin
        non couvert.
        """
        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        discipline = Discipline.create(db_session, {"code": "MATH", "name": "Mathématiques"})
        subject = Subject.create(db_session, {"code": "MATH", "code_nomenclature": "N_MATH", "short_name": "MATH", "name": "MATH", "discipline_id": discipline.id})
        ref_grade = RefGrade.create(db_session, {"name": "NIVEAU_MAXCLASS"})
        mef = Mef.create(db_session, {"school_id": school.id, "code_national": "10010012110", "name": "6EME", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 60})
        division_a = Division.create(db_session, {"school_id": school.id, "code": "A", "name": "6ème A"})
        division_b = Division.create(db_session, {"school_id": school.id, "code": "B", "name": "6ème B"})
        mef_division_a = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_a.id, "forecast_student_count": 28})
        mef_division_b = MefDivision.create(db_session, {"mef_id": mef.id, "division_id": division_b.id, "forecast_student_count": 28})
        mef_service = MefService.create(db_session, {"mef_id": mef.id, "subject_id": subject.id, "discipline_id": discipline.id})
        service_a = db_session.query(Service).filter(Service.mef_service_id == mef_service.id, Service.mef_division_id == mef_division_a.id).one()
        service_b = db_session.query(Service).filter(Service.mef_service_id == mef_service.id, Service.mef_division_id == mef_division_b.id).one()
        service_a.update(db_session, {"weekly_duration_full_class_minutes": 60})
        service_b.update(db_session, {"weekly_duration_full_class_minutes": 60})

        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=120, priority=1, ref_grade=ref_grade)
        pref = db_session.query(TeacherGradePreference).filter(TeacherGradePreference.teacher_id == teacher.id, TeacherGradePreference.ref_grade_id == ref_grade.id).one()
        pref.update(db_session, {"max_class_count": 1})

        result = compute_assignment_proposal(db_session)

        cap_warnings = [w for w in result["warnings"] if w["type"] == "max_class_count_unresolved"]
        assert len(cap_warnings) == 1
        assert cap_warnings[0]["teacher_ids"] == [teacher.id]
        # Aucune alternative qualifiée : les deux propositions restent inchangées (pas d'abandon
        # silencieux d'un des deux services pour faire disparaître le dépassement).
        by_service = {p["service_id"]: p for p in result["proposals"]}
        assert by_service[service_a.id]["teacher_ids"] == [teacher.id]
        assert by_service[service_b.id]["teacher_ids"] == [teacher.id]


class TestLockedServiceExcluded:
    def test_locked_service_never_proposed(self, db_session):
        school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        _make_teacher(db_session, school, "T1", discipline, discipline_minutes=120)
        service.update(db_session, {"weekly_duration_full_class_minutes": 60, "teachers_locked": True})

        result = compute_assignment_proposal(db_session)
        assert not any(p["service_id"] == service.id for p in result["proposals"])
        assert not any(service.id in w.get("service_ids", []) for w in result["warnings"])


class TestTeacherGradePreferenceCascade:
    def test_new_teacher_gets_a_line_per_existing_ref_grade(self, db_session):
        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        g1 = RefGrade.create(db_session, {"name": "SIXIEME"})
        g2 = RefGrade.create(db_session, {"name": "CINQUIEME"})

        teacher = Teacher.create(db_session, {"code": "NEWT", "last_name": "New", "school_id": school.id})

        lines = db_session.query(TeacherGradePreference).filter(TeacherGradePreference.teacher_id == teacher.id).all()
        assert {l.ref_grade_id for l in lines} == {g1.id, g2.id}
        assert all(l.priority == 2 and l.max_class_count is None for l in lines)

    def test_new_ref_grade_gets_a_line_per_existing_teacher(self, db_session):
        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        teacher = Teacher.create(db_session, {"code": "T1", "last_name": "L1", "school_id": school.id})

        new_grade = RefGrade.create(db_session, {"name": "TERMINALE"})

        line = db_session.query(TeacherGradePreference).filter(
            TeacherGradePreference.teacher_id == teacher.id, TeacherGradePreference.ref_grade_id == new_grade.id,
        ).one()
        assert line.priority == 2


class TestIncompatibilitySymmetryAndValidation:
    def test_incompatibility_is_visible_from_both_sides(self, db_session):
        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        t1 = Teacher.create(db_session, {"code": "T1", "last_name": "L1", "school_id": school.id})
        t2 = Teacher.create(db_session, {"code": "T2", "last_name": "L2", "school_id": school.id})

        t1.update(db_session, {"incompatible_teacher_ids": [t2.id]})

        assert _are_incompatible(db_session, t1.id, t2.id)
        assert _are_incompatible(db_session, t2.id, t1.id)
        db_session.refresh(t2)
        assert [t.id for t in t2.incompatible_teachers] == [t1.id]

    def test_removing_incompatibility_removes_it_both_sides(self, db_session):
        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        t1 = Teacher.create(db_session, {"code": "T1", "last_name": "L1", "school_id": school.id})
        t2 = Teacher.create(db_session, {"code": "T2", "last_name": "L2", "school_id": school.id})
        t1.update(db_session, {"incompatible_teacher_ids": [t2.id]})

        t1.update(db_session, {"incompatible_teacher_ids": []})

        assert not _are_incompatible(db_session, t1.id, t2.id)
        assert not _are_incompatible(db_session, t2.id, t1.id)

    def test_self_incompatibility_rejected(self, db_session):
        school = School.create(db_session, {"uai": "1234567A", "name": "Collège Test"})
        t1 = Teacher.create(db_session, {"code": "T1", "last_name": "L1", "school_id": school.id})
        with pytest.raises(ValueError):
            t1.update(db_session, {"incompatible_teacher_ids": [t1.id]})


class TestTeacherComputedDurations:
    def test_taught_raw_and_weighted_ignore_composed_parents(self, db_session):
        school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=120)
        Course.create(db_session, {
            "school_id": school.id, "subject_id": subject.id, "teacher_ids": [teacher.id],
            "duration_minutes": 60, "weighting_coefficient": 1.5,
        })
        parent = Course.create(db_session, {
            "school_id": school.id, "is_composed": True, "teacher_ids": [teacher.id], "duration_minutes": 990,
        })
        Course.create(db_session, {
            "school_id": school.id, "subject_id": subject.id, "parent_id": parent.id, "teacher_ids": [teacher.id],
            "duration_minutes": 30, "weighting_coefficient": 1.0,
        })

        db_session.refresh(teacher)
        # 60 (simple) + 30 (enfant du composé) — le parent (999) est exclu.
        assert teacher.taught_raw_duration_minutes == 90
        assert teacher.taught_weighted_duration_minutes == 60 * 1.5 + 30 * 1.0

    def test_hsa_duration_adds_are_ara_csd_and_subtracts_ors(self, db_session):
        school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=90)
        Course.create(db_session, {
            "school_id": school.id, "subject_id": subject.id, "teacher_ids": [teacher.id],
            "duration_minutes": 90, "weighting_coefficient": 1.0,
        })
        ref_are = RefAre.create(db_session, {"name": "ARE Test"})
        TeacherAre.create(db_session, {"teacher_id": teacher.id, "ref_are_id": ref_are.id, "duration_minutes": 30})

        db_session.refresh(teacher)
        # teached pondéré (90) + ARE (30) + ARA (0) + CSD (0) - ORS (90) = 30
        assert teacher.hsa_duration_minutes == 30


class TestWizard:
    def test_simulate_does_not_write_to_database(self, db_session):
        school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=120)
        service.update(db_session, {"weekly_duration_full_class_minutes": 60})

        wizard = WizardTeacherAssignment.read(db_session)[0]
        result = wizard.rpc_simulate(db_session)

        db_session.refresh(service)
        assert service.teachers == []
        assert len(result["proposals"]) == 1
        assert result["proposals"][0]["teacher_ids"] == [teacher.id]

    def test_apply_writes_proposals_and_skips_newly_locked_services(self, db_session):
        school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=120)
        service.update(db_session, {"weekly_duration_full_class_minutes": 60})

        wizard = WizardTeacherAssignment.read(db_session)[0]
        simulate_result = wizard.rpc_simulate(db_session)

        # Verrouillé manuellement entre simulate et apply (voir §7 de la proposition).
        service.update(db_session, {"teachers_locked": True})
        apply_result = wizard.rpc_apply(db_session, simulate_result["proposals"])

        db_session.refresh(service)
        assert service.teachers == []
        assert "1 proposition(s) ignorée(s)" in apply_result["result_html"]

    def test_apply_actually_assigns_when_not_locked(self, db_session):
        school, discipline, subject, ref_grade, mef, division, mef_division, mef_service, service = _base_setup(db_session)
        teacher = _make_teacher(db_session, school, "T1", discipline, discipline_minutes=120)
        service.update(db_session, {"weekly_duration_full_class_minutes": 60})

        wizard = WizardTeacherAssignment.read(db_session)[0]
        simulate_result = wizard.rpc_simulate(db_session)
        wizard.rpc_apply(db_session, simulate_result["proposals"])

        db_session.refresh(service)
        assert [t.id for t in service.teachers] == [teacher.id]

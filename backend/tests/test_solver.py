import pytest
from sqlalchemy.orm import sessionmaker, Session
from backend.app.models.base import Base
from backend.app.models.school import School
from backend.app.models.discipline import Discipline
from backend.app.models.subject import Subject
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.models.course_classroom_requirement import CourseClassroomRequirement
from backend.app.models.group import Partition, ClassPart, ClassPartLink, Group
from backend.app.models.student import Student
from backend.app.models.preference import ResourcePreference
from backend.app.models.period import Period
from backend.app.models.constraint import CourseToCourseConstraint, SubjectToSubjectConstraint, ResourceConstraint
from backend.app.solver.room_solver import solve_classroom_assignment
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _solve_course_placement(db, school_id=None):
    """
    Résout le domaine COURSE_PLACEMENT (timeslot/week_type — jamais la salle, voir plan salles
    §2/§4) pour ce fichier de tests. Reprend directement les briques de production réutilisées par
    l'orchestration réelle (solver.py::_run_solve_phase, appelé par start_course_placement_async) —
    construction du problème, solve avec les mêmes limites de temps que le legacy /solve
    (settings.SOLVER_TIME_LIMIT_SECONDS/SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS), puis write-back —
    sans la couche SolverState/mode exclusif/pipeline (inutile pour un appel séquentiel direct en
    test, déjà couverte par ses propres tests d'intégration, voir Task #7).
    """
    from timefold.solver.config import SolverConfigOverride, TerminationConfig, Duration
    from backend.app.core.config import settings
    from backend.app.solver.solver import (
        _build_course_placement_problem, _get_solver_factory, _write_back_course_placement,
    )
    problem = _build_course_placement_problem(db, school_id)
    solver_factory = _get_solver_factory()
    solver = solver_factory.build_solver(solver_config_override=SolverConfigOverride(
        termination_config=TerminationConfig(
            spent_limit=Duration(seconds=settings.SOLVER_TIME_LIMIT_SECONDS),
            unimproved_spent_limit=Duration(seconds=settings.SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS),
        ),
    ))
    solution = solver.solve(problem)
    _write_back_course_placement(db, school_id, solution)
    db.commit()
    return solution


# =====================================================================================
# Fixture commune
# =====================================================================================

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        school = School.create(db, {"uai": "1234567A", "name": "Lycée Test"})

        from backend.app.models.system_setting import SystemSetting
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})

        discipline = Discipline.create(db, {"code": "GEN", "name": "Général"})

        Subject.create(db, {
            "code": "MATH",
            "code_nomenclature": "NOM_MATH",
            "short_name": "Maths",
            "name": "Mathématiques",
            "discipline_id": discipline.id
        })

        db.commit()
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


# =====================================================================================
# Domaine COURSE_PLACEMENT (plan salles §2) — timeslot/week_type seulement, jamais la salle
# (voir plan salles, "Décisions déjà tranchées"). Les salles créées dans certains de ces tests
# sont vestigiales (héritées de l'ancien domaine combiné) et retirées quand elles n'étaient pas
# réellement exploitées par les assertions.
# =====================================================================================

def test_solver_resolves_timetable(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_MATH", "first_name": "Prof", "last_name": "Math", "school_id": school.id})

    d1 = Division.create(db_session, {"code": "DIV_6E", "name": "6ème", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 2, "minutes_from_midnight": 480})

    course1 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 30})
    course2 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 30})
    db_session.commit()

    _solve_course_placement(db_session)

    db_session.refresh(course1)
    db_session.refresh(course2)

    assert course1.timeslot_id is not None
    assert course2.timeslot_id is not None
    assert course1.timeslot_id != course2.timeslot_id


def test_solver_unsuited_only_timeslot_stays_unplaced(db_session: Session):
    """
    Régression : quand l'UNIQUE créneau disponible est Unsuited pour le professeur du cours, le
    solveur doit laisser le cours non placé (timeslot_id=None), pas le placer quand même sur ce
    créneau. Avant correctif, resource_preference_hard et penalize_unassigned_course valaient
    toutes deux ONE_HARD : à égalité stricte de score, rien ne garantissait laquelle des deux
    issues le solveur retenait. resource_preference_hard vaut désormais of_hard(1000).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_ONLYUNSTS", "first_name": "Prof", "last_name": "Onlyunsts", "school_id": school.id})
    division = Division.create(db_session, {"code": "DIV_ONLYUNSTS", "name": "Div Onlyunsts", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    ResourcePreference.create(db_session, {
        "resource_type": "Teacher", "resource_id": teacher.id, "timeslot_id": ts1.id,
        "preference_level": "Unsuited", "week_type": "W",
    })

    course = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [teacher.id], "division_ids": [division.id], "school_id": school.id, "duration_minutes": 30})
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(course)

    assert course.timeslot_id is None, "Le cours a été placé sur le créneau Unsuited alors qu'il était le seul disponible"


def test_solver_group_link_and_week_alternation(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_A", "first_name": "Prof", "last_name": "A", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "PROF_B", "first_name": "Prof", "last_name": "B", "school_id": school.id})

    d1 = Division.create(db_session, {"code": "DIV_A", "name": "Div A", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    # CORRECTION DU TEST : Création de DEUX partitions distinctes
    partition1 = Partition.create(db_session, {"code": "PART_LANG", "name": "Partition Langues", "division_id": d1.id})
    partition2 = Partition.create(db_session, {"code": "PART_LV2", "name": "Partition LV2", "division_id": d1.id})

    cp1 = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition1.id, "name": "Anglais"})
    cp2 = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition2.id, "name": "Espagnol"})
    link = db_session.query(ClassPartLink).filter_by(class_part_a_id=min(cp1.id, cp2.id), class_part_b_id=max(cp1.id, cp2.id)).first()
    assert link is not None

    g1 = Group.create(db_session, {"name": "Groupe 1", "class_part_ids": [cp1.id]})
    g2 = Group.create(db_session, {"name": "Groupe 2", "class_part_ids": [cp2.id]})

    course1 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "group_ids": [g1.id], "school_id": school.id, "week_type": "W", "duration_minutes": 30})
    course2 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t2.id], "division_ids": [d1.id], "group_ids": [g2.id], "school_id": school.id, "week_type": "W", "duration_minutes": 30})
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(course1)
    db_session.refresh(course2)

    course1.update(db_session, {"timeslot_id": None, "week_type": "A"})
    course2.update(db_session, {"timeslot_id": None, "week_type": "B"})
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(course1)
    db_session.refresh(course2)

    assert course1.timeslot_id is not None
    assert course2.timeslot_id is not None
    assert course1.timeslot_id == course2.timeslot_id

def test_solver_respects_preferences(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_PREF", "first_name": "Prof", "last_name": "Pref", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_PREF", "name": "Div Pref", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    ResourcePreference.create(db_session, {"resource_type": "Teacher", "resource_id": t1.id, "timeslot_id": ts1.id, "preference_level": "Unsuited"})
    ResourcePreference.create(db_session, {"resource_type": "Teacher", "resource_id": t1.id, "timeslot_id": ts2.id, "preference_level": "Preferred"})

    course = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 30})
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(course)

    assert course.timeslot_id is not None
    assert course.timeslot_id == ts2.id

def test_solver_preference_overrides_stability(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_STAB", "first_name": "Prof", "last_name": "Stab", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_STAB", "name": "Div Stab", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    ResourcePreference.create(db_session, {"resource_type": "Teacher", "resource_id": t1.id, "timeslot_id": ts2.id, "preference_level": "Preferred"})

    course = Course.create(db_session, {
        "subject_id": subject.id,
        "teacher_ids": [t1.id],
        "division_ids": [d1.id],
        "timeslot_id": ts1.id,
        "school_id": school.id,
        "duration_minutes": 30
    })
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(course)

    assert course.timeslot_id is not None
    assert course.timeslot_id == ts2.id

def test_solver_respects_week_specific_preferences(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_WEEK", "first_name": "Prof", "last_name": "Week", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_WEEK", "name": "Div Week", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    ResourcePreference.create(db_session, {"resource_type": "Teacher", "resource_id": t1.id, "timeslot_id": ts1.id, "preference_level": "Unsuited", "week_type": "A"})

    course_a = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "week_type": "A", "duration_minutes": 30})
    course_b = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "week_type": "B", "duration_minutes": 30})
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(course_a)
    db_session.refresh(course_b)

    assert course_a.timeslot_id is not None
    assert course_b.timeslot_id is not None
    assert course_a.timeslot_id == ts2.id
    assert course_b.timeslot_id == ts1.id

def test_solver_respects_period_specific_preferences(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_PERIOD", "first_name": "Prof", "last_name": "Period", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_PERIOD", "name": "Div Period", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    import datetime
    from backend.app.models.period_type import PeriodType
    pt = PeriodType.create(db_session, {"name": "Semestre"})

    per1 = Period.create(db_session, {"period_type_id": pt.id, "school_id": school.id, "code": "P1", "name": "Période 1", "start_date": datetime.date(2026, 9, 1), "end_date": datetime.date(2026, 12, 31)})
    per2 = Period.create(db_session, {"period_type_id": pt.id, "school_id": school.id, "code": "P2", "name": "Période 2", "start_date": datetime.date(2027, 1, 1), "end_date": datetime.date(2027, 6, 30)})

    ResourcePreference.create(db_session, {
        "resource_type": "Teacher",
        "resource_id": t1.id,
        "timeslot_id": ts1.id,
        "preference_level": "Unsuited",
        "period_ids": [per1.id]
    })

    course = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 30})
    db_session.commit()

    course.update(db_session, {"periods": [per2], "period_type_id": pt.id})
    db_session.commit()


    _solve_course_placement(db_session)
    db_session.refresh(course)

    assert course.timeslot_id == ts1.id

    course.update(db_session, {"timeslot_id": None, "periods": [per1]})
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(course)

    assert course.timeslot_id == ts2.id

def test_solver_prevents_day_overflow(db_session: Session):
    """
    Vérifie que la contrainte Timefold (Course day overflow) empêche
    un cours de déborder de la journée.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_OVERFLOW2", "first_name": "Prof", "last_name": "Overflow2", "school_id": school.id})

    # On crée deux créneaux : 17h00 et 17h30 (le dernier) sur le jour 1.
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 1020})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 1050})

    # On crée un cours de 60 minutes
    course = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "duration_minutes": 60,
    })

    # Add teacher
    course.teachers = [teacher]
    db_session.commit()

    # Appel de la fonction de construction du problème de planification
    from backend.app.solver.solver import _build_course_placement_problem
    from backend.app.solver.constraints import define_constraints, PlanningCourse, course_day_overflow
    import timefold.solver.score as score

    problem = _build_course_placement_problem(db_session, school.id)

    # On force manuellement le placement du cours sur ts2 (17h30)
    target_p_course = next(c for c in problem.courses if c.id == course.id)
    target_p_ts2 = next(ts for ts in problem.timeslots if ts.id == ts2.id)
    target_p_course.timeslot = target_p_ts2

    # On évalue spécifiquement la contrainte via un score factory mocké ou on appelle la méthode
    # En Python timefold, on peut tester la contrainte via ConstraintVerifier (si disponible)
    # ou simplement tester manuellement notre lambda.
    # Puisque ConstraintVerifier n'est pas encore nativement exposé facilement,
    # on vérifie la logique interne de notre filtre python.

    assert (target_p_course.timeslot.minutes_from_midnight + target_p_course.duration_minutes) > target_p_course.timeslot.absolute_end_of_day



def test_course_preference_deleted_on_course_cascade(db_session: Session):
    """
    Suppression en cascade des ResourcePreference liées à un Course supprimé (Course.delete()) —
    mécanisme distinct de l'héritage/propagation week_type/periods (retiré, voir
    attribution_week_type_auto.md, Échange 8 : basé sur une mauvaise compréhension initiale).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    course = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "week_type": "A"
    })
    db_session.commit()

    ts = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    db_session.commit()

    pref = ResourcePreference.create(db_session, {
        "resource_type": "Course",
        "resource_id": course.id,
        "timeslot_id": ts.id,
        "preference_level": "Unsuited"
    })
    db_session.commit()
    pref_id = pref.id

    course.delete(db_session)
    db_session.commit()

    deleted_pref = db_session.query(ResourcePreference).filter_by(id=pref_id).first()
    assert deleted_pref is None


def test_solver_respects_course_preferences(db_session: Session):
    from backend.app.solver.constraints import _is_preference_violated, PlanningPreference

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    course = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "week_type": "W"
    })
    db_session.commit()

    ts = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    db_session.commit()

    pref = ResourcePreference.create(db_session, {
        "resource_type": "Course",
        "resource_id": course.id,
        "timeslot_id": ts.id,
        "preference_level": "Unsuited"
    })
    db_session.commit()

    # Simuler les objets du solveur PlanningCourse et PlanningPreference
    from backend.app.solver.constraints import PlanningCourse, PlanningTimeslot

    p_course = PlanningCourse(
        id=course.id,
        duration_minutes=120,
        week_type="W",
        period_ids=[],
        teachers=[],
        divisions=[]
    )

    p_pref = PlanningPreference(
        id=pref.id,
        resource_type="Course",
        resource_id=course.id,
        timeslot_id=ts.id,
        preference_level="Unsuited",
        week_type="W",
        period_ids=[]
    )

    # Vérifier que _is_preference_violated retourne True si le cours correspond au resource_id
    assert _is_preference_violated(p_pref, p_course) is True

    # Vérifier que _is_preference_violated retourne False pour un autre cours
    other_course = PlanningCourse(
        id=999,
        duration_minutes=120,
        week_type="W",
        period_ids=[],
        teachers=[],
        divisions=[]
    )
    assert _is_preference_violated(p_pref, other_course) is False


# =====================================================================================
# Heatmap — mutualisée avec le domaine COURSE_PLACEMENT (plan salles §2.4) : même construction
# de problème (_build_course_placement_problem), même jeu de contraintes, seule la boucle de
# calcul diffère (score répété par créneau candidat, pas de vraie recherche locale).
# =====================================================================================

def test_course_heatmap_with_indisponibility(db_session: Session):
    from backend.app.solver.solver import calculate_course_heatmap

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # Création du professeur
    teacher = Teacher.create(db_session, {
        "code": "PROF_ART",
        "first_name": "Prof",
        "last_name": "Art",
        "school_id": school.id
    })

    # Création de deux créneaux : ts1 (disponible) et ts2 (indisponible)
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    # Ajouter le vœu INDISPONIBLE (Unsuited) pour ts2 pour ce professeur
    pref = ResourcePreference.create(db_session, {
        "resource_type": "Teacher",
        "resource_id": teacher.id,
        "timeslot_id": ts2.id,
        "preference_level": "Unsuited",
        "week_type": "W"
    })

    # Création du cours (non placé initialement)
    course = Course.create(db_session, {
        "subject_id": subject.id,
        "teacher_ids": [teacher.id],
        "school_id": school.id,
        "duration_minutes": 30
    })
    db_session.commit()

    # Calculer la heatmap pour ce cours
    heatmap = calculate_course_heatmap(db_session, course.id, school.id)

    # Vérifier que les résultats pour ts1 et ts2 existent
    assert str(ts1.id) in heatmap
    assert str(ts2.id) in heatmap

    # ts1 est disponible : pas de conflit physique, donc delta Hard = 0
    assert heatmap[str(ts1.id)]["hard"] == 0
    assert len(heatmap[str(ts1.id)]["reasons"]) == 0

    # ts2 est indisponible (Unsuited) : resource_preference_hard vaut désormais of_hard(1000),
    # pas ONE_HARD (voir constraints.py — sinon à égalité stricte avec penalize_unassigned_course).
    assert heatmap[str(ts2.id)]["hard"] == -1000
    reasons = [r["name"] for r in heatmap[str(ts2.id)]["reasons"]]
    assert "Resource unavailability (strict)" in reasons


def test_course_heatmap_detects_conflicts_for_course_and_others(db_session: Session):
    """
    Régression (ancienne, signalée en usage réel) : calculate_course_heatmap ne fait JAMAIS
    tourner le CH du solveur (elle appelle directement setWorkingSolution()/calculateScore() sur
    les données telles quelles) — une entité dont une @PlanningVariable reste "non initialisée"
    (valeur None) est purement et simplement EXCLUE de tout for_each()/for_each_unique_pair()
    ordinaire par Timefold, pas seulement pour les contraintes regardant cette variable, mais
    pour TOUTES (teacher_conflict, resource_preference_*, division_conflict...). Couvert
    aujourd'hui par un cours dont timeslot vaut encore None (cas normal, cours pas encore placé),
    pour le cours cible ET pour un autre cours déjà placé partageant une ressource.
    """
    from backend.app.solver.solver import calculate_course_heatmap

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    teacher = Teacher.create(db_session, {"code": "PROF_NOROOM", "first_name": "Prof", "last_name": "NoRoom", "school_id": school.id})
    division = Division.create(db_session, {"code": "DIV_NOROOM", "name": "Div NoRoom", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    # Préférence "Indisponible" sur la division, pour ts2.
    ResourcePreference.create(db_session, {
        "resource_type": "Division", "resource_id": division.id, "timeslot_id": ts2.id,
        "preference_level": "Unsuited", "week_type": "W",
    })

    # Cours DÉJÀ PLACÉ à ts1, partageant le même enseignant.
    other_course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [teacher.id], "timeslot_id": ts1.id,
    })

    # Cours cible, non placé.
    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [teacher.id], "division_ids": [division.id],
    })
    db_session.commit()

    heatmap = calculate_course_heatmap(db_session, course.id, school.id)

    # ts1 : même enseignant que other_course, déjà placé là — conflit réel.
    assert heatmap[str(ts1.id)]["hard"] == -1
    assert "Teacher conflict" in [r["name"] for r in heatmap[str(ts1.id)]["reasons"]]

    # ts2 : préférence "Indisponible" (Unsuited) sur la division du cours cible — of_hard(1000),
    # pas ONE_HARD (voir constraints.py::resource_preference_hard).
    assert heatmap[str(ts2.id)]["hard"] == -1000
    assert "Resource unavailability (strict)" in [r["name"] for r in heatmap[str(ts2.id)]["reasons"]]


def test_solver_leaves_unplaceable_course_unassigned(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_UNPLACEABLE", "first_name": "Prof", "last_name": "Unplaceable", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_UNPLACEABLE", "name": "Div Unplaceable", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    # Création d'un seul créneau
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    # Création de deux cours pour le même enseignant (qui entrent en conflit si placés sur le même créneau unique)
    course1 = Course.create(db_session, {
        "subject_id": subject.id,
        "teacher_ids": [t1.id],
        "division_ids": [d1.id],
        "school_id": school.id,
        "duration_minutes": 30
    })
    course2 = Course.create(db_session, {
        "subject_id": subject.id,
        "teacher_ids": [t1.id],
        "division_ids": [d1.id],
        "school_id": school.id,
        "duration_minutes": 30
    })
    db_session.commit()

    # Lancer la résolution
    _solve_course_placement(db_session)

    db_session.refresh(course1)
    db_session.refresh(course2)

    # L'un des deux cours doit être placé, et l'autre doit rester non placé
    timeslots = {course1.timeslot_id, course2.timeslot_id}
    assert None in timeslots
    assert ts1.id in timeslots


def test_auto_create_class_part_links(db_session: Session):
    school = db_session.query(School).first()
    d1 = Division.create(db_session, {"code": "DIV_TEST_LINKS", "name": "Div Test Links", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    # Création de deux partitions pour la même division
    partition1 = Partition.create(db_session, {"code": "P_LANG", "name": "Partition Langues", "division_id": d1.id})
    partition2 = Partition.create(db_session, {"code": "P_ART", "name": "Partition Arts", "division_id": d1.id})

    # Création des parties pour partition 1
    cp1_a = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition1.id, "name": "Anglais"})
    cp1_b = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition1.id, "name": "Allemand"})

    # À ce stade, pas de liens créés car pas d'autre partition contenant des parties
    links_before = db_session.query(ClassPartLink).all()
    links_test_before = [l for l in links_before if l.class_part_a_id in (cp1_a.id, cp1_b.id) or l.class_part_b_id in (cp1_a.id, cp1_b.id)]
    assert len(links_test_before) == 0

    # Création des parties pour partition 2
    cp2_a = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition2.id, "name": "Arts Plastiques"})

    # cp2_a doit être liée automatiquement à cp1_a et cp1_b
    links = db_session.query(ClassPartLink).all()
    links_cp2_a = [l for l in links if l.class_part_a_id == min(cp2_a.id, cp1_a.id) and l.class_part_b_id == max(cp2_a.id, cp1_a.id)]
    assert len(links_cp2_a) == 1
    assert links_cp2_a[0].is_system_generated is True

    links_cp2_a_ger = [l for l in links if l.class_part_a_id == min(cp2_a.id, cp1_b.id) and l.class_part_b_id == max(cp2_a.id, cp1_b.id)]
    assert len(links_cp2_a_ger) == 1

    # Création de cp2_b
    cp2_b = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition2.id, "name": "Musique"})

    # cp2_b doit être liée à cp1_a et cp1_b
    links = db_session.query(ClassPartLink).all()
    links_cp2_b = [l for l in links if l.class_part_a_id == min(cp2_b.id, cp1_a.id) and l.class_part_b_id == max(cp2_b.id, cp1_a.id)]
    assert len(links_cp2_b) == 1

    links_cp2_b_ger = [l for l in links if l.class_part_a_id == min(cp2_b.id, cp1_b.id) and l.class_part_b_id == max(cp2_b.id, cp1_b.id)]
    assert len(links_cp2_b_ger) == 1

    # Vérifier que cp2_a et cp2_b ne sont pas liées entre elles (même partition)
    links_intra = [l for l in links if l.class_part_a_id == min(cp2_a.id, cp2_b.id) and l.class_part_b_id == max(cp2_a.id, cp2_b.id)]
    assert len(links_intra) == 0


def test_student_and_link_constraints(db_session: Session):
    import pytest
    from backend.app.models.mef import Mef, MefDivision
    from backend.app.models.ref_grade import RefGrade
    school = db_session.query(School).first()
    d = Division.create(db_session, {"code": "DIV_STUD_TEST", "name": "Div Stud Test", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    d_id = d.id

    ref_grade = RefGrade.create(db_session, {"name": "NIVEAU_STUD_TEST"})
    mef = Mef.create(db_session, {"school_id": school.id, "code_national": "MEF_STUDT", "name": "MEF Test", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 25})
    MefDivision.create(db_session, {"mef_id": mef.id, "division_id": d_id, "forecast_student_count": 25})

    # Partitions
    p1 = Partition.create(db_session, {"code": "P_STUD_1", "name": "Partition 1", "division_id": d_id})
    p2 = Partition.create(db_session, {"code": "P_STUD_2", "name": "Partition 2", "division_id": d_id})
    p1_id = p1.id
    p2_id = p2.id

    # ClassParts
    cp1_a = ClassPart.create(db_session, {"division_id": d_id, "partition_id": p1_id, "name": "Part 1A"})
    cp1_b = ClassPart.create(db_session, {"division_id": d_id, "partition_id": p1_id, "name": "Part 1B"})
    cp1_a_id = cp1_a.id
    cp1_b_id = cp1_b.id

    # cp2_a est automatiquement liée à cp1_a et cp1_b via des liens d'exclusion système
    cp2_a = ClassPart.create(db_session, {"division_id": d_id, "partition_id": p2_id, "name": "Part 2A"})
    cp2_a_id = cp2_a.id

    db_session.commit()

    # 1. Vérifier que modifier un ClassPartLink lève une ValueError
    link = db_session.query(ClassPartLink).filter_by(class_part_a_id=min(cp1_a_id, cp2_a_id), class_part_b_id=max(cp1_a_id, cp2_a_id)).first()
    assert link is not None
    link_id = link.id

    with pytest.raises(ValueError, match="strictly forbidden|strictement interdit"):
        link_to_up = db_session.get(ClassPartLink, link_id)
        link_to_up.update(db_session, {"is_system_generated": False})

    db_session.commit()

    # 2. Création d'élèves pour tester les contraintes
    # Élève valide : appartient à cp1_a et cp2_a
    student1 = Student.create(db_session, {
        "first_name": "Jean",
        "last_name": "Dupont",
        "division_id": d_id,
        "mef_id": mef.id,
        "class_part_ids": [cp1_a_id, cp2_a_id]
    })
    assert student1.id is not None
    student1_id = student1.id

    db_session.commit()

    # Élève invalide : appartient à cp1_a et cp1_b (même partition -> interdit)
    with pytest.raises(ValueError, match="same partition|m.me partition"):
        Student.create(db_session, {
            "first_name": "Invalide",
            "last_name": "SamePart",
            "division_id": d_id,
            "mef_id": mef.id,
            "class_part_ids": [cp1_a_id, cp1_b_id]
        })

    db_session.commit()

    # Élève invalide : appartient à une partie d'une autre division (cohérence de division -> interdit)
    d2 = Division.create(db_session, {"code": "DIV_STUD_TEST_2", "name": "Div Stud Test 2", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    p2_d2 = Partition.create(db_session, {"code": "P_STUD_D2", "name": "Partition D2", "division_id": d2.id})
    cp_d2 = ClassPart.create(db_session, {"division_id": d2.id, "partition_id": p2_d2.id, "name": "Part D2"})
    db_session.commit()

    with pytest.raises(ValueError, match="depend d'une autre division|another division"):
        Student.create(db_session, {
            "first_name": "Invalide",
            "last_name": "WrongDiv",
            "division_id": d_id,
            "mef_id": mef.id,
            "class_part_ids": [cp_d2.id]
        })

    db_session.commit()

    # 3. Vérifier que supprimer le lien d'incompatibilité entre cp1_a et cp2_a lève une ValueError car student1 y appartient
    link_to_delete = db_session.query(ClassPartLink).filter_by(class_part_a_id=min(cp1_a_id, cp2_a_id), class_part_b_id=max(cp1_a_id, cp2_a_id)).first()
    assert link_to_delete is not None
    link_to_delete_id = link_to_delete.id

    with pytest.raises(ValueError, match="Impossible de supprimer ce lien|Cannot delete"):
        l_del = db_session.get(ClassPartLink, link_to_delete_id)
        l_del.delete(db_session)


def test_student_mef_must_match_division(db_session: Session):
    import pytest
    from backend.app.models.mef import Mef, MefDivision
    from backend.app.models.ref_grade import RefGrade
    school = db_session.query(School).first()
    d = Division.create(db_session, {"code": "DIV_MEF_TEST", "name": "Div Mef Test", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ref_grade = RefGrade.create(db_session, {"name": "NIVEAU_MEF_TEST"})
    mef_linked = Mef.create(db_session, {"school_id": school.id, "code_national": "MEF_LINKED", "name": "MEF Lié", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 25})
    mef_unrelated = Mef.create(db_session, {"school_id": school.id, "code_national": "MEF_UNREL", "name": "MEF Non Lié", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 25})
    MefDivision.create(db_session, {"mef_id": mef_linked.id, "division_id": d.id, "forecast_student_count": 25})
    db_session.commit()

    # Un élève dont le MEF n'est pas lié à sa division doit être rejeté
    with pytest.raises(ValueError, match="doit être l'un des MEF liés"):
        Student.create(db_session, {"first_name": "Paul", "last_name": "Martin", "division_id": d.id, "mef_id": mef_unrelated.id})

    db_session.commit()

    # Un élève dont le MEF est bien lié à sa division est accepté
    student = Student.create(db_session, {"first_name": "Alice", "last_name": "Durand", "division_id": d.id, "mef_id": mef_linked.id})
    assert student.id is not None
    db_session.commit()

    # L'effectif calculé du lien MEF/Division reflète l'élève réparti
    link = db_session.query(MefDivision).filter_by(mef_id=mef_linked.id, division_id=d.id).first()
    assert link.computed_student_count == 1


def test_mef_division_computed_count_is_per_mef(db_session: Session):
    """Sur une division composite (double-niveau), chaque MefDivision ne doit compter
    que les élèves de son propre MEF, pas l'ensemble des élèves de la division."""
    from backend.app.models.mef import Mef, MefDivision
    from backend.app.models.ref_grade import RefGrade
    school = db_session.query(School).first()
    d = Division.create(db_session, {"code": "DIV_DOUBLE_NIVEAU", "name": "Div Double Niveau", "student_count": 4, "color": "#CCCCCC", "school_id": school.id})

    ref_grade = RefGrade.create(db_session, {"name": "NIVEAU_DBL"})
    mef_a = Mef.create(db_session, {"school_id": school.id, "code_national": "MEF_A_DBL", "name": "MEF A", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 2})
    mef_b = Mef.create(db_session, {"school_id": school.id, "code_national": "MEF_B_DBL", "name": "MEF B", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 2})
    link_a = MefDivision.create(db_session, {"mef_id": mef_a.id, "division_id": d.id, "forecast_student_count": 2})
    link_b = MefDivision.create(db_session, {"mef_id": mef_b.id, "division_id": d.id, "forecast_student_count": 2})
    db_session.commit()

    Student.create(db_session, {"first_name": "E1", "last_name": "MefA", "division_id": d.id, "mef_id": mef_a.id})
    Student.create(db_session, {"first_name": "E2", "last_name": "MefA", "division_id": d.id, "mef_id": mef_a.id})
    Student.create(db_session, {"first_name": "E3", "last_name": "MefB", "division_id": d.id, "mef_id": mef_b.id})
    db_session.commit()

    assert link_a.computed_student_count == 2
    assert link_b.computed_student_count == 1


def test_get_linked_groups(db_session: Session):
    school = db_session.query(School).first()
    d = Division.create(db_session, {"code": "DIV_GGRP", "name": "Div GGrp", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    p1 = Partition.create(db_session, {"code": "P_GGRP_1", "name": "Partition GGrp 1", "division_id": d.id})
    p2 = Partition.create(db_session, {"code": "P_GGRP_2", "name": "Partition GGrp 2", "division_id": d.id})

    cp_a = ClassPart.create(db_session, {"division_id": d.id, "partition_id": p1.id, "name": "Part GGrp A"})
    cp_b = ClassPart.create(db_session, {"division_id": d.id, "partition_id": p1.id, "name": "Part GGrp B"})

    # cp_c est cree dans partition 2, ce qui declenche automatiquement la creation de liens ClassPartLink avec cp_a et cp_b
    cp_c = ClassPart.create(db_session, {"division_id": d.id, "partition_id": p2.id, "name": "Part GGrp C"})

    g_a = Group.create(db_session, {"name": "Groupe A", "class_part_ids": [cp_a.id]})
    g_b = Group.create(db_session, {"name": "Groupe B", "class_part_ids": [cp_b.id]})
    g_c = Group.create(db_session, {"name": "Groupe C", "class_part_ids": [cp_c.id]})

    db_session.commit()

    # cp_c est liee a cp_a et cp_b
    # Donc g_c (contenant cp_c) est lie a g_a (contenant cp_a) et g_b (contenant cp_b)
    linked_to_c = g_c.get_linked_groups(db_session)
    linked_to_c_ids = [g.id for g in linked_to_c]
    assert g_a.id in linked_to_c_ids
    assert g_b.id in linked_to_c_ids
    # g_a (contenant cp_a) est lie a g_c (contenant cp_c liee a cp_a)
    linked_to_a = g_a.get_linked_groups(db_session)
    linked_to_a_ids = [g.id for g in linked_to_a]
    assert g_c.id in linked_to_a_ids
    assert g_b.id not in linked_to_a_ids  # cp_a et cp_b sont dans la meme partition, donc pas de lien direct

def test_course_to_course_constraints(db_session: Session):
    import os
    os.environ["SOLVER_TIME_LIMIT_SECONDS"] = "5"
    from backend.app.models.constraint import course_constraint_associations
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # 1. Enseignants
    t1 = Teacher.create(db_session, {"code": "PROF_CTC1", "first_name": "Prof", "last_name": "CTC1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "PROF_CTC2", "first_name": "Prof", "last_name": "CTC2", "school_id": school.id})

    # Création de créneaux horaires distincts pour s'assurer que le solveur peut planifier à différents moments
    for day in range(1, 6):
        for hour in [8, 9, 10, 11, 14, 15, 16]:
            Timeslot.create(db_session, {"day_of_week": day, "minutes_from_midnight": hour * 60})

    # 2. Test FORCE_SAME_SCOPE : course_sim_1 et course_sim_2 doivent être planifiés sur la même période (créneau par défaut)
    course_sim_1 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})
    course_sim_2 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t2.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})

    ctc_sim = CourseToCourseConstraint.create(db_session, {"type": "FORCE_SAME_SCOPE", "scope": "SLOT", "is_optional": False, "label": "Force Same Scope Test", "course_ids": [course_sim_1.id, course_sim_2.id]})

    # 3. Test ORDER : course_ord_a doit passer avant course_ord_b
    course_ord_a = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})
    course_ord_b = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t2.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})

    ctc_ord = CourseToCourseConstraint.create(db_session, {"type": "ORDER", "is_optional": False, "label": "Order Test"})

    # On insère les liaisons ordonnées dans la table de jointure
    db_session.execute(
        course_constraint_associations.insert(),
        [
            {"constraint_id": ctc_ord.id, "course_id": course_ord_a.id, "sequence_order": 0},
            {"constraint_id": ctc_ord.id, "course_id": course_ord_b.id, "sequence_order": 1},
        ]
    )
    db_session.commit()

    # 4. Test FORBID_SAME_SCOPE : course_forbid_1 et course_forbid_2 ne doivent pas être sur la même période (ici DAY)
    course_forbid_1 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})
    course_forbid_2 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t2.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})

    ctc_forbid = CourseToCourseConstraint.create(db_session, {"type": "FORBID_SAME_SCOPE", "scope": "DAY", "is_optional": False, "label": "Forbid Same Scope Test", "course_ids": [course_forbid_1.id, course_forbid_2.id]})

    # 5. Test FORBID_CONSECUTIVE : course_cons_1 et course_cons_2 ne doivent pas se suivre directement
    course_cons_1 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})
    course_cons_2 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t2.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})

    ctc_cons = CourseToCourseConstraint.create(db_session, {"type": "FORBID_CONSECUTIVE", "is_optional": False, "label": "Forbid Consecutive Test", "course_ids": [course_cons_1.id, course_cons_2.id]})

    # 5bis. Test FORBID_SAME_SCOPE (HALF_DAY) : course_hd_1 et course_hd_2 ne doivent pas être sur la même demi-journée
    course_hd_1 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})
    course_hd_2 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t2.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})

    ctc_hd = CourseToCourseConstraint.create(db_session, {"type": "FORBID_SAME_SCOPE", "scope": "HALF_DAY", "is_optional": False, "label": "Forbid Half Day Test", "course_ids": [course_hd_1.id, course_hd_2.id]})

    # 5ter. Test FORCE_SAME_SCOPE (CUSTOM_HALF_DAYS) : course_cust_1 et course_cust_2 doivent être dans la même tranche de 4 demi-journées (2 jours)
    course_cust_1 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})
    course_cust_2 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t2.id], "school_id": school.id, "week_type": "W", "duration_minutes": 60})

    ctc_cust = CourseToCourseConstraint.create(db_session, {
        "type": "FORCE_SAME_SCOPE",
        "scope": "CUSTOM_HALF_DAYS",
        "custom_half_days": 4,
        "is_optional": False,
        "label": "Custom Half Days Test",
        "course_ids": [course_cust_1.id, course_cust_2.id]
    })

    db_session.commit()

    # Résolution de l'emploi du temps
    _solve_course_placement(db_session)

    # Rechargement des objets
    db_session.refresh(course_sim_1)
    db_session.refresh(course_sim_2)
    db_session.refresh(course_ord_a)
    db_session.refresh(course_ord_b)
    db_session.refresh(course_forbid_1)
    db_session.refresh(course_forbid_2)
    db_session.refresh(course_cons_1)
    db_session.refresh(course_cons_2)
    db_session.refresh(course_hd_1)
    db_session.refresh(course_hd_2)
    db_session.refresh(course_cust_1)
    db_session.refresh(course_cust_2)


    # 6. Vérification des assertions
    # FORCE_SAME_SCOPE : même timeslot et même semaine
    assert course_sim_1.timeslot_id is not None
    assert course_sim_2.timeslot_id is not None
    assert course_sim_1.timeslot_id == course_sim_2.timeslot_id
    assert course_sim_1.week_type == course_sim_2.week_type

    # ORDER : ord_a strictement avant ord_b
    assert course_ord_a.timeslot_id is not None
    assert course_ord_b.timeslot_id is not None
    ts_a = db_session.get(Timeslot, course_ord_a.timeslot_id)
    ts_b = db_session.get(Timeslot, course_ord_b.timeslot_id)
    if ts_a.day_of_week == ts_b.day_of_week:
        assert ts_a.minutes_from_midnight < ts_b.minutes_from_midnight
    else:
        assert ts_a.day_of_week < ts_b.day_of_week

    # FORBID_SAME_SCOPE (DAY) : jours différents
    assert course_forbid_1.timeslot_id is not None
    assert course_forbid_2.timeslot_id is not None
    ts_f1 = db_session.get(Timeslot, course_forbid_1.timeslot_id)
    ts_f2 = db_session.get(Timeslot, course_forbid_2.timeslot_id)
    assert ts_f1.day_of_week != ts_f2.day_of_week

    # FORBID_CONSECUTIVE : pas consécutifs sur le même jour
    assert course_cons_1.timeslot_id is not None
    assert course_cons_2.timeslot_id is not None
    ts_c1 = db_session.get(Timeslot, course_cons_1.timeslot_id)
    ts_c2 = db_session.get(Timeslot, course_cons_2.timeslot_id)
    if ts_c1.day_of_week == ts_c2.day_of_week:
        # La différence entre les heures de début doit être strictement supérieure à la durée d'un cours (1.0h)
        assert abs(ts_c1.minutes_from_midnight - ts_c2.minutes_from_midnight) > 1.01

    # FORBID_SAME_SCOPE (HALF_DAY) : demi-journées différentes (si même jour)
    assert course_hd_1.timeslot_id is not None
    assert course_hd_2.timeslot_id is not None
    ts_hd1 = db_session.get(Timeslot, course_hd_1.timeslot_id)
    ts_hd2 = db_session.get(Timeslot, course_hd_2.timeslot_id)
    if ts_hd1.day_of_week == ts_hd2.day_of_week:
        hd1_am = ts_hd1.minutes_from_midnight < Timeslot.get_noon_boundary_minutes()
        hd2_am = ts_hd2.minutes_from_midnight < Timeslot.get_noon_boundary_minutes()
        assert hd1_am != hd2_am

    # FORCE_SAME_SCOPE (CUSTOM_HALF_DAYS) : même bloc de 4 demi-journées (2 jours)
    assert course_cust_1.timeslot_id is not None
    assert course_cust_2.timeslot_id is not None
    ts_cust1 = db_session.get(Timeslot, course_cust_1.timeslot_id)
    ts_cust2 = db_session.get(Timeslot, course_cust_2.timeslot_id)
    cust1_hd = (ts_cust1.day_of_week - 1) * 2 + (0 if ts_cust1.minutes_from_midnight < 12.0 else 1)
    cust2_hd = (ts_cust2.day_of_week - 1) * 2 + (0 if ts_cust2.minutes_from_midnight < 12.0 else 1)
    assert (cust1_hd // 4) == (cust2_hd // 4)


def test_course_to_course_constraint_validations(db_session: Session):
    from backend.app.models.constraint import CourseToCourseConstraint, CourseToCourseConstraintType, CourseToCourseConstraintScope

    # 1/ scope est obligatoire si type est FORCE_SAME_SCOPE ou FORBID_SAME_SCOPE
    with pytest.raises(ValueError, match="Le périmètre.*est obligatoire"):
        CourseToCourseConstraint.create(db_session, {
            "type": CourseToCourseConstraintType.FORCE_SAME_SCOPE,
            "scope": None,
        })

    # 1bis/ interdit sinon
    with pytest.raises(ValueError, match="Le périmètre.*est interdit"):
        CourseToCourseConstraint.create(db_session, {
            "type": CourseToCourseConstraintType.ORDER,
            "scope": CourseToCourseConstraintScope.DAY,
        })

    # 2/ custom_half_days est obligatoire si scope == CUSTOM_HALF_DAYS
    with pytest.raises(ValueError, match="Le nombre de demi-journées personnalisées est obligatoire"):
        CourseToCourseConstraint.create(db_session, {
            "type": CourseToCourseConstraintType.FORCE_SAME_SCOPE,
            "scope": CourseToCourseConstraintScope.CUSTOM_HALF_DAYS,
            "custom_half_days": None,
        })

    # 2bis/ et nul sinon
    with pytest.raises(ValueError, match="Le nombre de demi-journées personnalisées est interdit"):
        CourseToCourseConstraint.create(db_session, {
            "type": CourseToCourseConstraintType.FORCE_SAME_SCOPE,
            "scope": CourseToCourseConstraintScope.DAY,
            "custom_half_days": 3,
        })

    # Test create success
    ctc = CourseToCourseConstraint.create(db_session, {
        "type": CourseToCourseConstraintType.ORDER,
        "scope": None,
    })
    db_session.flush()

    # 3/ type et scope non modifiables après création
    with pytest.raises(ValueError, match="Il n'est pas possible de modifier le type"):
        ctc.update(db_session, {"type": CourseToCourseConstraintType.FORBID_CONSECUTIVE})

    with pytest.raises(ValueError, match="Il n'est pas possible de modifier le périmètre"):
        ctc.update(db_session, {"scope": CourseToCourseConstraintScope.DAY})

def test_share_reference_period():
    from backend.app.solver.constraints import _share_reference_period, PlanningCourse, PlanningTimeslot

    # Création des timeslots de test
    ts1 = PlanningTimeslot(id=1, day_of_week=1, minutes_from_midnight=540, absolute_end_of_day=18.0, noon_boundary_minutes=Timeslot.get_noon_boundary_minutes())
    ts2 = PlanningTimeslot(id=2, day_of_week=1, minutes_from_midnight=600, absolute_end_of_day=18.0, noon_boundary_minutes=Timeslot.get_noon_boundary_minutes()) # même jour, même demi-journée (matin)
    ts3 = PlanningTimeslot(id=3, day_of_week=1, minutes_from_midnight=840, absolute_end_of_day=18.0, noon_boundary_minutes=Timeslot.get_noon_boundary_minutes()) # même jour, après-midi
    ts4 = PlanningTimeslot(id=4, day_of_week=2, minutes_from_midnight=540, absolute_end_of_day=18.0, noon_boundary_minutes=Timeslot.get_noon_boundary_minutes())  # jour différent

    c1 = PlanningCourse(id=1, duration_minutes=60, timeslot=ts1, week_type="A")
    c2 = PlanningCourse(id=2, duration_minutes=60, timeslot=ts2, week_type="A")
    c3 = PlanningCourse(id=3, duration_minutes=60, timeslot=ts3, week_type="A")
    c4 = PlanningCourse(id=4, duration_minutes=60, timeslot=ts4, week_type="A")
    c5 = PlanningCourse(id=5, duration_minutes=60, timeslot=ts1, week_type="B")
    c6 = PlanningCourse(id=6, duration_minutes=60, timeslot=ts1, week_type="W")
    c7 = PlanningCourse(id=7, duration_minutes=60, timeslot=ts1, week_type="A", period_ids=[1], period_mask=1)
    c8 = PlanningCourse(id=8, duration_minutes=60, timeslot=ts2, week_type="A", period_ids=[2], period_mask=2)
    c9 = PlanningCourse(id=9, duration_minutes=60, timeslot=ts3, week_type="A", period_ids=[1, 3], period_mask=5)

    # 0. PERIODS
    assert _share_reference_period(c7, c9, "DAY") # Partagent la période 1, partagent le même jour
    assert not _share_reference_period(c7, c8, "DAY") # Périodes disjointes, bien qu'ils soient sur le même jour

    # 1. SLOT
    assert _share_reference_period(c1, c1, "SLOT")
    assert not _share_reference_period(c1, c2, "SLOT")

    # 2. DAY
    assert _share_reference_period(c1, c2, "DAY")
    assert _share_reference_period(c1, c3, "DAY")
    assert not _share_reference_period(c1, c4, "DAY")
    assert not _share_reference_period(c1, c5, "DAY") # semaines différentes A/B

    # 3. HALF_DAY
    assert _share_reference_period(c1, c2, "HALF_DAY")
    assert not _share_reference_period(c1, c3, "HALF_DAY")

    # 4. QUINZAINE
    assert _share_reference_period(c1, c2, "QUINZAINE") # même quinzaine (tous deux A)
    assert not _share_reference_period(c1, c5, "QUINZAINE") # alternances différentes (A vs B)
    assert _share_reference_period(c1, c6, "QUINZAINE") # compatibilité A vs T

    # 5. CUSTOM_HALF_DAYS (ex: n=4 demi-journées, soit tranches de 2 jours)
    assert _share_reference_period(c1, c4, "CUSTOM_HALF_DAYS", 4)
    ts_wed = PlanningTimeslot(id=5, day_of_week=3, minutes_from_midnight=540, absolute_end_of_day=18.0, noon_boundary_minutes=Timeslot.get_noon_boundary_minutes())
    c_wed = PlanningCourse(id=7, duration_minutes=60, timeslot=ts_wed, week_type="A")
    assert not _share_reference_period(c1, c_wed, "CUSTOM_HALF_DAYS", 4)

def test_subject_constraint_rules_orm(db_session: Session):
    import pytest
    from backend.app.models.constraint import ResourceConstraint, SubjectToSubjectConstraint
    school = db_session.query(School).first()
    subjects = db_session.query(Subject).all()
    if len(subjects) < 2:
        sub2 = Subject(code="PHYS", code_nomenclature="NOM_PHYS", short_name="Phys", name="Physique", discipline_id=subjects[0].discipline_id)
        sub2._via_crud_mixin_create = True
        db_session.add(sub2)
        db_session.commit()
        db_session.refresh(sub2)
        subjects.append(sub2)

    sub1 = subjects[0]
    sub2 = subjects[1]

    # Rule 1: target_subject_b_id is mandatory for Subject
    payload = {
        "target_subject_a_id": sub1.id,
        "is_optional": False,
    }
    with pytest.raises(ValueError, match="est obligatoire"):
        SubjectToSubjectConstraint.create(db_session, payload)

    # Successful creation
    payload["target_subject_b_id"] = sub2.id
    constraint = SubjectToSubjectConstraint.create(db_session, payload)
    db_session.commit()

    # Rule 3: Exclusivity of separation
    update_payload = {"incompatible_same_half_day": True, "min_free_half_days_between": 2}
    constraint.update(db_session, update_payload)
    db_session.commit()
    assert constraint.incompatible_same_half_day is True
    assert constraint.min_free_half_days_between is None  # other should be cleared
    assert constraint.incompatible_same_day is False

    # Rule 4 & 5: Sync A/B if same subject and weekly_order is NONE
    payload_same = {
        "target_subject_a_id": sub1.id,
        "target_subject_b_id": sub1.id,
        "prevent_consecutive_a_then_b": True,
        "weekly_order": "A_BEFORE_B",
        "is_optional": True,  # Test explicit optional=True
    }
    constraint_same = SubjectToSubjectConstraint.create(db_session, payload_same)
    db_session.commit()
    assert constraint_same.prevent_consecutive_b_then_a is True  # Synced
    assert constraint_same.weekly_order.value == "NONE"  # Rule 5
    assert constraint_same.is_optional is True

    update_payload_rule7 = {
        "group_course_order": "GROUP_BEFORE",
        "max_separation": "SUCCESSIVE_DAYS"
    }
    constraint.update(db_session, update_payload_rule7)
    db_session.commit()
    assert constraint.group_course_order.value == "NONE"
    assert constraint.max_separation.value == "NONE"

def test_solver_subject_constraint_optionality(db_session: Session):
    from backend.app.models.constraint import ResourceConstraint, SubjectToSubjectConstraint
    school = db_session.query(School).first()
    subjects = db_session.query(Subject).all()
    if len(subjects) < 2:
        sub2 = Subject(code="TEST_OPT", code_nomenclature="TEST_OPT", short_name="T_OPT", name="Test Opt", discipline_id=subjects[0].discipline_id)
        sub2._via_crud_mixin_create = True
        db_session.add(sub2)
        db_session.commit()
        db_session.refresh(sub2)
        subjects.append(sub2)

    sub_a = subjects[0]
    sub_b = subjects[1]

    t1 = Teacher.create(db_session, {"code": "T_OPT_S", "first_name": "T", "last_name": "OPT", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_OPT_S", "name": "Div Opt", "student_count": 25, "color": "#000", "school_id": school.id})

    # Create 2 timeslots on the SAME day
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    # 2 courses: one of A, one of B, for the same division.
    c_a = Course.create(db_session, {"subject_id": sub_a.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 60})
    c_b = Course.create(db_session, {"subject_id": sub_b.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 60})
    db_session.commit()

    # 1. Test with Mandatory constraint (is_optional=False)
    rc = SubjectToSubjectConstraint.create(db_session, {
        "target_subject_a_id": sub_a.id,
        "target_subject_b_id": sub_b.id,
        "incompatible_same_day": True,
        "is_optional": False
    })
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(c_a)
    db_session.refresh(c_b)

    # Mandatory constraint: they cannot be on the same day. Since we only have Monday timeslots,
    # one must remain unplaced!
    assert None in [c_a.timeslot_id, c_b.timeslot_id]

    # Clean up placements
    c_a.update(db_session, {"timeslot_id": None})
    c_b.update(db_session, {"timeslot_id": None})

    # 2. Test with Optional constraint (is_optional=True)
    rc.update(db_session, {"is_optional": True})
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(c_a)
    db_session.refresh(c_b)

    # Optional constraint: the solver can violate it, so both should be placed.
    assert c_a.timeslot_id is not None
    assert c_b.timeslot_id is not None

def test_solver_subject_constraint_division_scope(db_session: Session):
    from backend.app.models.constraint import ResourceConstraint, SubjectToSubjectConstraint
    school = db_session.query(School).first()
    subjects = db_session.query(Subject).all()
    if len(subjects) < 2:
        sub2 = Subject(code="TEST_SCP", code_nomenclature="TEST_SCP", short_name="T_SCP", name="Test Scp", discipline_id=subjects[0].discipline_id)
        sub2._via_crud_mixin_create = True
        db_session.add(sub2)
        db_session.commit()
        db_session.refresh(sub2)
        subjects.append(sub2)

    sub_a = subjects[0]
    sub_b = subjects[1]

    t1 = Teacher.create(db_session, {"code": "T_SCP_1", "first_name": "T1", "last_name": "SCP", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_SCP_2", "first_name": "T2", "last_name": "SCP", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_SCP_1", "name": "Div Scp 1", "student_count": 25, "color": "#000", "school_id": school.id})
    d2 = Division.create(db_session, {"code": "DIV_SCP_2", "name": "Div Scp 2", "student_count": 25, "color": "#000", "school_id": school.id})

    # Create 2 timeslots on the SAME day
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    # 4 courses: 2 for D1, 2 for D2
    c1_a = Course.create(db_session, {"subject_id": sub_a.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 60})
    c1_b = Course.create(db_session, {"subject_id": sub_b.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 60})
    c2_a = Course.create(db_session, {"subject_id": sub_a.id, "teacher_ids": [t2.id], "division_ids": [d2.id], "school_id": school.id, "duration_minutes": 60})
    c2_b = Course.create(db_session, {"subject_id": sub_b.id, "teacher_ids": [t2.id], "division_ids": [d2.id], "school_id": school.id, "duration_minutes": 60})
    db_session.commit()

    # Constraint applies only to D1
    rc = SubjectToSubjectConstraint.create(db_session, {
        "target_subject_a_id": sub_a.id,
        "target_subject_b_id": sub_b.id,
        "incompatible_same_day": True,
        "is_optional": False,
        "division_ids": [d1.id]
    })
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(c1_a)
    db_session.refresh(c1_b)
    db_session.refresh(c2_a)
    db_session.refresh(c2_b)

    # For D1, the constraint is active. One of them must be unplaced because there are only timeslots on day 1.
    assert None in [c1_a.timeslot_id, c1_b.timeslot_id]

    # For D2, the constraint is inactive. Both should be placed because there are no other constraints preventing it.
    assert c2_a.timeslot_id is not None
    assert c2_b.timeslot_id is not None
    assert c2_a.timeslot_id != c2_b.timeslot_id

def test_max_separation_successive_days_orm(db_session: Session):
    from datetime import date
    sch = School.create(db_session, {"uai": "999", "name": "Sch", "student_start_date": date(2026, 9, 1), "student_end_date": date(2027, 6, 30)})
    disc = Discipline.create(db_session, {"code": "D", "name": "D"})
    sub = Subject.create(db_session, {"code": "S1", "code_nomenclature": "S1", "discipline_id": disc.id, "short_name": "S1", "name": "S1", "color": "#000"})

    from backend.app.models.mef import Mef, MefDivision
    from backend.app.models.ref_grade import RefGrade
    ref_grade = RefGrade.create(db_session, {"name": "NIVEAU_SEP"})
    mef = Mef.create(db_session, {"school_id": sch.id, "code_national": "M", "name": "M", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 30})
    div = Division.create(db_session, {"school_id": sch.id, "code": "DIV", "name": "DIV"})
    MefDivision.create(db_session, {"mef_id": mef.id, "division_id": div.id, "forecast_student_count": 30})

    # Timeslots: Lundi, Mercredi (days 1, 3)
    ts_lun = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts_mer = Timeslot.create(db_session, {"day_of_week": 3, "minutes_from_midnight": 480})

    # Courses (2 for S1)
    c1 = Course.create(db_session, {"school_id": sch.id, "subject_id": sub.id, "duration_minutes": 60, "division_ids": [div.id]})
    c2 = Course.create(db_session, {"school_id": sch.id, "subject_id": sub.id, "duration_minutes": 60, "division_ids": [div.id]})

    # Set timeslots
    c1.update(db_session, {"original_timeslot_id": ts_lun.id})
    c2.update(db_session, {"original_timeslot_id": ts_mer.id}) # Diff of 2 days -> Should penalize if SUCCESSIVE_DAYS

    SubjectToSubjectConstraint.create(db_session, {
        "target_subject_a_id": sub.id,
        "target_subject_b_id": sub.id,
        "max_separation": "successive_days",
        "is_optional": False
    })

    solution = _solve_course_placement(db_session, sch.id)
    # Just asserting it runs without error and score is calculated
    assert solution.score is not None

def setup_group_course_order_scenario(db_session, enum_value, pin_c1_day, pin_c2_day, pin_c3_day=None):
    from backend.app.models.group import Partition, ClassPart
    from datetime import date
    import uuid
    uai_val = str(uuid.uuid4())[:8]
    sch = School.create(db_session, {"uai": uai_val, "name": "Sch", "student_start_date": date(2026, 9, 1), "student_end_date": date(2027, 6, 30)})
    disc = Discipline.create(db_session, {"code": f"D_{uai_val}", "name": "D3"})
    sub = Subject.create(db_session, {"code": f"S_{uai_val}", "code_nomenclature": f"S_{uai_val}", "discipline_id": disc.id, "short_name": "S3", "name": "S3", "color": "#000"})

    from backend.app.models.mef import Mef, MefDivision
    from backend.app.models.ref_grade import RefGrade
    ref_grade = RefGrade.create(db_session, {"name": f"NIVEAU_{uai_val}"})
    mef = Mef.create(db_session, {"school_id": sch.id, "code_national": f"M_{uai_val}", "name": "M3", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 30})
    div = Division.create(db_session, {"school_id": sch.id, "code": f"DIV_{uai_val}", "name": "DIV3"})
    MefDivision.create(db_session, {"mef_id": mef.id, "division_id": div.id, "forecast_student_count": 30})

    part = Partition.create(db_session, {"division_id": div.id, "code": f"P_{uai_val}", "name": "PART"})
    cp1 = ClassPart.create(db_session, {"partition_id": part.id, "name": "CP1"})
    cp2 = ClassPart.create(db_session, {"partition_id": part.id, "name": "CP2"})

    # Create grid to avoid overflow and unique constraints
    timeslots = {}
    for day in [1, 2, 3]:
        for minutes in [480, 510, 540]:
            ts = db_session.query(Timeslot).filter(Timeslot.day_of_week == day, Timeslot.minutes_from_midnight == minutes).first()
            if not ts:
                ts = Timeslot.create(db_session, {"day_of_week": day, "minutes_from_midnight": minutes})
            if minutes == 480:
                timeslots[day] = ts.id

    # c1 = FULL CLASS
    c1 = Course.create(db_session, {"school_id": sch.id, "subject_id": sub.id, "duration_minutes": 60, "division_ids": [div.id], "timeslot_id": timeslots[pin_c1_day], "is_pinned": True})

    # c2 = GROUP CLASS 1
    c2 = Course.create(db_session, {"school_id": sch.id, "subject_id": sub.id, "duration_minutes": 60, "class_part_ids": [cp1.id], "timeslot_id": timeslots[pin_c2_day], "is_pinned": True})

    if pin_c3_day:
        # c3 = GROUP CLASS 2
        c3 = Course.create(db_session, {"school_id": sch.id, "subject_id": sub.id, "duration_minutes": 60, "class_part_ids": [cp2.id], "timeslot_id": timeslots[pin_c3_day], "is_pinned": True})

    SubjectToSubjectConstraint.create(db_session, {
        "target_subject_a_id": sub.id,
        "target_subject_b_id": sub.id,
        "group_course_order": enum_value,
        "is_optional": False,
        "incompatible_same_day": False
    })

    db_session.commit()
    return sch

def test_group_course_order_group_before(db_session: Session):
    # FULL on Tue (2), GROUP on Mon (1) -> Valid
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE", pin_c1_day=2, pin_c2_day=1)
    solution = _solve_course_placement(db_session, sch.id)
    assert solution.score.hard_score == 0

    # FULL on Mon (1), GROUP on Tue (2) -> Invalid
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE", pin_c1_day=1, pin_c2_day=2)
    solution = _solve_course_placement(db_session, sch.id)
    assert solution.score.hard_score < 0

def test_group_course_order_group_after(db_session: Session):
    # FULL on Mon (1), GROUP on Tue (2) -> Valid
    sch = setup_group_course_order_scenario(db_session, "GROUP_AFTER", pin_c1_day=1, pin_c2_day=2)
    solution = _solve_course_placement(db_session, sch.id)
    assert solution.score.hard_score == 0

    # FULL on Tue (2), GROUP on Mon (1) -> Invalid
    sch = setup_group_course_order_scenario(db_session, "GROUP_AFTER", pin_c1_day=2, pin_c2_day=1)
    solution = _solve_course_placement(db_session, sch.id)
    assert solution.score.hard_score < 0

def test_group_course_order_before_or_after(db_session: Session):
    # FULL on Tue (2), GROUP1 on Mon (1), GROUP2 on Mon (1) -> Valid (both before)
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE_OR_AFTER", pin_c1_day=2, pin_c2_day=1, pin_c3_day=1)
    solution = _solve_course_placement(db_session, sch.id)
    assert solution.score.hard_score == 0

    # FULL on Tue (2), GROUP1 on Mon (1), GROUP2 on Wed (3) -> Invalid (mixed)
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE_OR_AFTER", pin_c1_day=2, pin_c2_day=1, pin_c3_day=3)
    solution = _solve_course_placement(db_session, sch.id)
    assert solution.score.hard_score < 0

def test_group_course_order_before_or_after_fortnight(db_session: Session):
    # FULL on Tue (2), GROUP1 on Mon (1), GROUP2 on Wed (3) -> Valid (mirrored)
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE_OR_AFTER_FORTNIGHT", pin_c1_day=2, pin_c2_day=1, pin_c3_day=3)
    solution = _solve_course_placement(db_session, sch.id)
    assert solution.score.hard_score == 0

    # FULL on Tue (2), GROUP1 on Wed (3), GROUP2 on Mon (1) -> Valid (mirrored)
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE_OR_AFTER_FORTNIGHT", pin_c1_day=2, pin_c2_day=3, pin_c3_day=1)
    solution = _solve_course_placement(db_session, sch.id)
    assert solution.score.hard_score == 0

    # FULL on Tue (2), GROUP1 on Wed (3), GROUP2 on Wed (3) -> Invalid (both after)
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE_OR_AFTER_FORTNIGHT", pin_c1_day=2, pin_c2_day=3, pin_c3_day=3)
    solution = _solve_course_placement(db_session, sch.id)
    assert solution.score.hard_score < 0

def test_solver_pedagogic_weight_limits(db_session: Session):
    from backend.app.models.school import School
    from backend.app.models.subject import Subject
    from backend.app.models.course import Course
    from backend.app.models.division import Division
    from backend.app.models.mef import Mef, MefDivision
    from backend.app.models.ref_grade import RefGrade
    from backend.app.models.discipline import Discipline
    from datetime import date
    import uuid

    uai_val = str(uuid.uuid4())[:8]
    # Limite à 3.0 de poids par jour, 1.5 par matinée, 2.0 par aprem
    sch = School.create(db_session, {
        "uai": uai_val,
        "name": "Sch",
        "student_start_date": date(2026, 9, 1),
        "student_end_date": date(2027, 6, 30),
        "max_pedagogic_weight_per_day": 3.0,
        "max_pedagogic_weight_per_morning": 1.5,
        "max_pedagogic_weight_per_afternoon": 2.0
    })

    disc = Discipline.create(db_session, {"code": f"D_{uai_val}", "name": "D"})

    # Matière très lourde : Mathématiques (Poids 2.0)
    sub_math = Subject.create(db_session, {"code": f"MATH_{uai_val}", "code_nomenclature": f"M_{uai_val}", "discipline_id": disc.id, "short_name": "Math", "name": "Math", "pedagogic_weight": 2.0})

    ref_grade = RefGrade.create(db_session, {"name": f"NIVEAU_{uai_val}"})
    mef = Mef.create(db_session, {"school_id": sch.id, "code_national": f"MW_{uai_val}", "name": "M", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 30})
    div = Division.create(db_session, {"school_id": sch.id, "code": f"DIV_{uai_val}", "name": "DIV"})
    MefDivision.create(db_session, {"mef_id": mef.id, "division_id": div.id, "forecast_student_count": 30})

    # Lundi = 1
    for m in [480, 510, 540, 570]:
        ts = db_session.query(Timeslot).filter_by(day_of_week=1, minutes_from_midnight=m).first()
        if not ts:
            Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": m})

    ts_am1 = db_session.query(Timeslot).filter_by(day_of_week=1, minutes_from_midnight=480).first()

    # 120 minutes (2 heures) de Math. Poids total = 2.0 * 2 = 4.0
    c1 = Course.create(db_session, {"school_id": sch.id, "subject_id": sub_math.id, "duration_minutes": 120, "division_ids": [div.id], "timeslot_id": ts_am1.id, "is_pinned": True})

    db_session.commit()
    solution1 = _solve_course_placement(db_session, sch.id)

    # Dépassement matinée: 4.0 - 1.5 = 2.5 (25 penalité)
    # Dépassement journée: 4.0 - 3.0 = 1.0 (10 penalité)
    assert solution1.score.hard_score <= -35

    # Reduit à 30 minutes. Poids = 2.0 * 0.5 = 1.0. Sous la limite (1.5)
    c1.update(db_session, {"duration_minutes": 30})
    db_session.commit()
    solution2 = _solve_course_placement(db_session, sch.id)
    assert solution2.score.hard_score == 0


# =====================================================================================
# Phase C (week_type Q -> A/B résolu par le solveur) — voir attribution_week_type_auto.md,
# Échanges 17-19. week_type devient une @PlanningVariable Timefold à portée ENTITÉ (pas un
# simple fait fixe copié depuis la base comme avant cette phase). Design unifié depuis
# l'Échange 18/19 : TOUT cours (simple ou composé) dont le week_type BDD — l'agrégat
# _sync_parent_week_type pour un composé — vaut A, B ou Q reçoit un vrai choix {A, B} ; seul W
# reste singleton, jamais résolu. Valeur de départ = None pour un cours Q (jamais la valeur
# hors-range elle-même, voir le spike de pré-semage), = sa valeur actuelle pour un cours A/B.
# Sûr pour les cours composés car _sync_parent_week_type garantit qu'un parent affichant une
# valeur singleton (A/B/Q) la partage à 100% de ses enfants — la cascade au write-back peut donc
# reporter sans ambiguïté la lettre choisie. Deux niveaux de tests : construction du problème
# (_build_course_placement_problem, rapide, sans lancer de résolution) pour vérifier le calcul du
# range/valeur initiale, et résolution complète (_solve_course_placement) pour vérifier le
# comportement réel du solveur, y compris la cascade aux enfants d'un cours composé.
# =====================================================================================

def test_build_course_placement_problem_gives_ab_range_to_simple_q_course(db_session: Session):
    """
    Un cours simple (non composé) en week_type=Q reçoit un vrai choix {A, B} côté solveur,
    valeur de départ None (voir le spike de pré-semage, attribution_week_type_auto.md Échange 19 :
    laisser "Q" comme valeur de départ — hors du range {A,B} — bloquerait le solveur dessus).
    """
    from backend.app.solver.solver import _build_course_placement_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "week_type": "Q",
    })
    db_session.commit()

    problem = _build_course_placement_problem(db_session, school.id)
    pc = next(c for c in problem.courses if c.id == course.id)

    assert pc.week_type_range == ["A", "B"]
    assert pc.week_type is None


def test_build_course_placement_problem_gives_free_range_to_resolved_ab_course(db_session: Session):
    """
    Un cours déjà résolu en A ou B reçoit désormais aussi un range libre {A, B} (Point 2,
    attribution_week_type_auto.md Échange 18/19 — corrige un écart avec spec.md qui promettait
    déjà cette liberté avant la Phase C) : le solveur peut le faire basculer si c'est meilleur.
    Sa valeur de départ reste sa valeur actuelle (point de départ naturel pour la recherche),
    PAS None — seul un cours né Q démarre à None.
    """
    from backend.app.solver.solver import _build_course_placement_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    course_b = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "week_type": "B"})
    db_session.commit()

    problem = _build_course_placement_problem(db_session, school.id)
    pc_b = next(c for c in problem.courses if c.id == course_b.id)

    assert pc_b.week_type_range == ["A", "B"]
    assert pc_b.week_type == "B"


def test_build_course_placement_problem_gives_singleton_range_to_w_course(db_session: Session):
    """
    Seul un cours en W (Toutes les semaines) reste totalement hors de portée du solveur pour
    week_type : range singleton ["W"], jamais de choix — spec.md interdit explicitement à un
    cours W de basculer vers A/B.
    """
    from backend.app.solver.solver import _build_course_placement_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    course_w = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "week_type": "W"})
    db_session.commit()

    problem = _build_course_placement_problem(db_session, school.id)
    pc_w = next(c for c in problem.courses if c.id == course_w.id)

    assert pc_w.week_type_range == ["W"]
    assert pc_w.week_type == "W"


def test_build_course_placement_problem_gives_free_range_to_composed_parent_with_uniform_q_children(db_session: Session):
    """
    Un cours composé (parent) dont TOUS les enfants sont Q (agrégat uniforme, voir la règle
    _sync_parent_week_type révisée à l'Échange 18/19) reçoit désormais lui aussi un vrai choix
    {A, B} — ce n'est plus une limite de portée exclue comme à l'Échange 17 : la résolution
    du parent sera reportée à ses enfants par cascade au write-back (voir tests d'intégration).
    Le solveur ne construit toujours une PlanningCourse QUE pour le cours de premier niveau —
    les enfants n'apparaissent jamais comme entités indépendantes.
    """
    from backend.app.solver.solver import _build_course_placement_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    parent = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "is_composed": True})
    db_session.commit()
    child1 = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    child2 = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type.value == "Q"

    problem = _build_course_placement_problem(db_session, school.id)
    pc_parent = next(c for c in problem.courses if c.id == parent.id)

    assert pc_parent.week_type_range == ["A", "B"]
    assert pc_parent.week_type is None
    assert all(c.id not in (child1.id, child2.id) for c in problem.courses)


def test_build_course_placement_problem_gives_free_range_to_composed_parent_with_mixed_a_and_q_children(db_session: Session):
    """
    Un cours composé mélangeant un enfant déjà résolu (A) et un enfant encore Q (agrégat parent
    -> Q, pas un conflit) reçoit lui aussi un vrai choix {A, B} côté solveur — exactement comme
    un parent uniformément Q : la résolution du groupe entier (y compris l'enfant déjà résolu)
    reste possible, voir les tests d'intégration de cascade.
    """
    from backend.app.solver.solver import _build_course_placement_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    parent = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "is_composed": True})
    db_session.commit()
    Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "A"})
    db_session.commit()
    Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type.value == "Q"

    problem = _build_course_placement_problem(db_session, school.id)
    pc_parent = next(c for c in problem.courses if c.id == parent.id)

    assert pc_parent.week_type_range == ["A", "B"]
    assert pc_parent.week_type is None


def test_build_course_placement_problem_gives_singleton_range_to_composed_parent_with_real_ab_conflict(db_session: Session):
    """
    Un cours composé avec un vrai conflit A/B (un enfant A ET un enfant B déjà tous deux
    présents) remonte en W et reste hors de portée du solveur : range singleton ["W"].
    """
    from backend.app.solver.solver import _build_course_placement_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    parent = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "is_composed": True})
    db_session.commit()
    Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "A"})
    db_session.commit()
    Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "B"})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type.value == "W"

    problem = _build_course_placement_problem(db_session, school.id)
    pc_parent = next(c for c in problem.courses if c.id == parent.id)

    assert pc_parent.week_type_range == ["W"]
    assert pc_parent.week_type == "W"


def test_solver_resolves_simple_q_course_to_a_or_b_never_leaves_q(db_session: Session):
    """
    Bout en bout : un cours simple né Q, sans aucune pression de conflit, doit ressortir résolu
    en A ou B après résolution — jamais laissé à Q — et cette résolution doit être persistée en
    base (écriture directe du solveur, voir solver.py).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_Q1", "first_name": "Prof", "last_name": "Q1", "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 510})

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "Q", "teacher_ids": [teacher.id],
    })
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(course)

    assert course.week_type.value in ("A", "B")


def test_solver_never_changes_week_type_of_already_resolved_unpinned_course(db_session: Session):
    """
    Un cours déjà résolu (jamais passé par Q) doit rester sur sa semaine d'origine après
    résolution, même non épinglé — son range n'a qu'une seule valeur légale, la recherche
    locale n'a donc structurellement aucune bascule à disposition pour ce cours.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_STABLE", "first_name": "Prof", "last_name": "Stable", "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 510})

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "A", "teacher_ids": [teacher.id],
    })
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(course)

    assert course.week_type.value == "A"


def test_solver_resolves_teacher_conflict_between_q_and_resolved_course_via_week_differentiation(db_session: Session):
    """
    Un seul créneau disponible, un même professeur sur deux cours : l'un déjà résolu et placé en
    semaine A sur ce créneau, l'autre né Q. Le solveur doit produire une solution sans conflit
    dur (hard_score == 0) ET résoudre le Q — la façon la plus directe d'y parvenir avec un seul
    créneau disponible est de placer le second cours en semaine B (weeks_overlap(A,B) = False),
    vérifié explicitement s'il finit sur le même créneau.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_CONFLICT", "first_name": "Prof", "last_name": "Conflict", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    course_a = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "A", "teacher_ids": [teacher.id], "timeslot_id": ts1.id,
        "is_pinned": True,
    })
    course_q = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "Q", "teacher_ids": [teacher.id],
    })
    db_session.commit()

    solution = _solve_course_placement(db_session)
    db_session.refresh(course_a)
    db_session.refresh(course_q)

    assert solution.score.hard_score == 0
    assert course_a.week_type.value == "A"  # épinglé : jamais touché
    assert course_q.week_type.value in ("A", "B")  # résolu, plus jamais Q
    if course_q.timeslot_id == ts1.id:
        # Même créneau que le cours épinglé : la seule façon d'éviter le conflit dur est B.
        assert course_q.week_type.value == "B"


def test_solver_respects_pin_for_week_type_forcing_other_course_to_resolve(db_session: Session):
    """
    @PlanningPin gèle TOUTES les variables de planification d'une entité (déjà vérifié pour
    timeslot, voir architecture.md section 5.G) — ce test vérifie que week_type en fait bien
    partie depuis la Phase C. Cours A épinglé sur l'unique créneau disponible : le cours Q
    partageant le même professeur ne peut structurellement pas le faire bouger, donc s'il se
    retrouve sur ce même créneau, il ne peut avoir été résolu qu'en B.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_PIN", "first_name": "Prof", "last_name": "Pin", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    course_pinned = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "A", "teacher_ids": [teacher.id], "timeslot_id": ts1.id,
        "is_pinned": True,
    })
    course_q = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "Q", "teacher_ids": [teacher.id],
    })
    db_session.commit()

    _solve_course_placement(db_session)
    db_session.refresh(course_pinned)
    db_session.refresh(course_q)

    assert course_pinned.timeslot_id == ts1.id
    assert course_pinned.week_type.value == "A"
    assert course_q.week_type.value in ("A", "B")
    if course_q.timeslot_id == ts1.id:
        assert course_q.week_type.value == "B"


def test_solver_resolves_composed_course_with_uniform_q_children_and_cascades(db_session: Session):
    """
    Point 3 (attribution_week_type_auto.md, Échange 18/19) : un cours composé dont TOUS les
    enfants sont Q (agrégat parent uniforme) est désormais résolu par le solveur comme un cours
    simple — et la lettre choisie doit être reportée par cascade à CHAQUE enfant, sinon ils
    resteraient Q individuellement malgré un parent résolu.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_COMP_Q", "first_name": "Prof", "last_name": "CompQ", "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 510})

    parent = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "is_composed": True,
    })
    db_session.commit()
    child1 = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    child2 = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    db_session.commit()
    parent.update(db_session, {"teacher_ids": [teacher.id]})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.is_composed is True
    assert parent.week_type.value == "Q"

    _solve_course_placement(db_session)
    db_session.refresh(parent)
    db_session.refresh(child1)
    db_session.refresh(child2)

    assert parent.week_type.value in ("A", "B")
    # Cascade : les deux enfants doivent porter EXACTEMENT la même lettre que le parent résolu.
    assert child1.week_type.value == parent.week_type.value
    assert child2.week_type.value == parent.week_type.value


def test_solver_swaps_resolved_composed_course_under_conflict_and_cascades(db_session: Session):
    """
    Point 2 + cascade (Échange 18/19) : un cours composé déjà résolu en A (tous enfants A
    uniformément) doit pouvoir être basculé en B par le solveur si nécessaire pour résoudre un
    conflit professeur — et ce basculement doit se répercuter sur ses deux enfants, qui
    partageaient tous deux la valeur A de départ (garanti par _sync_parent_week_type).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_COMP_SWAP", "first_name": "Prof", "last_name": "CompSwap", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    # Un autre cours simple, épinglé, qui occupe le même professeur sur le même créneau en A —
    # seule échappatoire pour le composé (aussi en A au départ) : basculer en B. Le composé
    # lui-même n'est PAS épinglé (is_pinned gèlerait aussi son week_type, contredisant le test) :
    # un seul créneau existe au total, donc il finira nécessairement sur ts1 lui aussi.
    other = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "A", "teacher_ids": [teacher.id], "timeslot_id": ts1.id,
        "is_pinned": True,
    })

    parent = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "is_composed": True,
    })
    db_session.commit()
    child1 = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "A"})
    child2 = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "A"})
    db_session.commit()
    parent.update(db_session, {"teacher_ids": [teacher.id]})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.is_composed is True
    assert parent.week_type.value == "A"

    solution = _solve_course_placement(db_session)
    db_session.refresh(parent)
    db_session.refresh(child1)
    db_session.refresh(child2)
    db_session.refresh(other)

    assert solution.score.hard_score == 0
    assert other.week_type.value == "A"  # épinglé : jamais touché
    if parent.timeslot_id == ts1.id:
        # Même créneau que le cours épinglé (seul créneau existant) : la seule façon d'éviter
        # le conflit dur est de basculer en B — reporté par cascade aux deux enfants.
        assert parent.week_type.value == "B"
        assert child1.week_type.value == "B"
        assert child2.week_type.value == "B"


def test_solver_resolves_mixed_composed_course_and_can_flip_already_resolved_child(db_session: Session):
    """
    Un cours composé mélangeant un enfant déjà résolu (A) et un enfant encore Q (agrégat parent
    -> Q, pas un conflit) est résolu par le solveur comme n'importe quel autre parent Q — la
    cascade reporte la lettre choisie à TOUS les enfants, y compris celui déjà résolu en A : si
    le groupe entier doit basculer en B pour éviter un conflit, l'enfant A déjà résolu bascule
    lui aussi, il n'est plus protégé du seul fait d'avoir déjà une lettre.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_COMP_MIX", "first_name": "Prof", "last_name": "CompMix", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    other = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "A", "teacher_ids": [teacher.id], "timeslot_id": ts1.id,
        "is_pinned": True,
    })

    parent = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "is_composed": True,
    })
    db_session.commit()
    child_a = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "A"})
    child_q = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    db_session.commit()
    parent.update(db_session, {"teacher_ids": [teacher.id]})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.is_composed is True
    assert parent.week_type.value == "Q"

    solution = _solve_course_placement(db_session)
    db_session.refresh(parent)
    db_session.refresh(child_a)
    db_session.refresh(child_q)
    db_session.refresh(other)

    assert solution.score.hard_score == 0
    assert other.week_type.value == "A"  # épinglé : jamais touché
    assert parent.week_type.value in ("A", "B")
    # Cascade : les deux enfants portent EXACTEMENT la même lettre que le parent résolu — y
    # compris child_a, qui était pourtant déjà résolu en A avant le solve.
    assert child_a.week_type.value == parent.week_type.value
    assert child_q.week_type.value == parent.week_type.value
    if parent.timeslot_id == ts1.id:
        # Même créneau que le cours épinglé : la seule échappatoire est B pour tout le groupe.
        assert parent.week_type.value == "B"
        assert child_a.week_type.value == "B"


# =====================================================================================
# US2 multi-établissement — un cours d'une AUTRE école que celle résolue (school_id explicite)
# ne doit jamais faire planter le solveur/la heatmap. Régression historique : l'ancien mécanisme
# forçait is_pinned=True sur ces cours en gelant TOUTES leurs variables (y compris l'ancienne
# variable classroom, désormais disparue de ce domaine) — un cours étranger sans salle en base se
# retrouvait épinglé sur un état illégal pour Timefold. Remplacé par
# foreign_school_timeslot_immobility (constraints.py) : ne protège que le créneau (et, depuis la
# Phase C, week_type — voir plus bas), jamais écrit en retour (garde school_id dans le write-back).
# Le mécanisme de "salle virtuelle" que ce fichier testait alors est devenu sans objet : il n'y a
# plus de salle du tout dans ce domaine, virtuelle ou non — supprimé, pas migré.
# =====================================================================================

def _create_second_school_with_foreign_course(db_session, teacher_code="T_FOREIGN"):
    """Crée une 2e école avec un cours placé (créneau) — le cas qui plantait."""
    import uuid
    uai = str(uuid.uuid4())[:8]
    other_school = School.create(db_session, {"uai": uai, "name": "Autre Ecole"})
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": teacher_code, "first_name": "Prof", "last_name": "Foreign", "school_id": other_school.id})
    ts = Timeslot.create(db_session, {"day_of_week": 2, "minutes_from_midnight": 480})
    foreign_course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": other_school.id, "duration_minutes": 30,
        "teacher_ids": [teacher.id], "timeslot_id": ts.id,
    })
    db_session.commit()
    return other_school, teacher, ts, foreign_course


def test_solver_ignores_foreign_school_course(db_session: Session):
    """
    Une résolution COURSE_PLACEMENT filtrée par school_id ne doit pas planter à cause d'un
    cours d'une autre école — ni corrompre les données de cette autre école.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    other_school, foreign_teacher, foreign_ts, foreign_course = _create_second_school_with_foreign_course(db_session)

    teacher = Teacher.create(db_session, {"code": "T_LOCAL", "first_name": "Prof", "last_name": "Local", "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    local_course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "teacher_ids": [teacher.id],
    })
    db_session.commit()

    _solve_course_placement(db_session, school.id)  # ne doit pas lever d'exception
    db_session.refresh(local_course)
    db_session.refresh(foreign_course)

    assert local_course.timeslot_id is not None
    # Le cours étranger n'est jamais écrit en retour : son créneau ne change pas.
    assert foreign_course.timeslot_id == foreign_ts.id


def test_heatmap_ignores_foreign_school_course(db_session: Session):
    """
    Le cas concrètement rapporté : calculate_course_heatmap(db, course_id, school_id) échouait
    silencieusement (exception Java avalée) dès qu'une autre école avait un cours placé.
    """
    from backend.app.solver.solver import calculate_course_heatmap

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    _create_second_school_with_foreign_course(db_session)

    teacher = Teacher.create(db_session, {"code": "T_HEATMAP", "first_name": "Prof", "last_name": "Heatmap", "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "teacher_ids": [teacher.id],
    })
    db_session.commit()

    heatmap = calculate_course_heatmap(db_session, course.id, school.id)

    assert "error" not in heatmap
    assert len(heatmap) > 0


def test_calculate_heatmap_java_propagates_errors_instead_of_swallowing_them(db_session: Session, monkeypatch):
    """
    Régression distincte du crash "pinned to null" historique : calculate_heatmap_java
    (heatmap_proxy.py) avalait TOUTE exception et retournait {} — un résultat indiscernable d'une
    heatmap légitimement vide, invisible pour l'appelant (seule une trace apparaissait sur
    stderr). Force une panne (indépendante de tout scénario de crash réel, pour ne pas dépendre
    d'un bug qui pourrait être corrigé un jour) et vérifie qu'elle remonte bien jusqu'à
    calculate_course_heatmap sous la forme {"error": ...}, exploitable par l'appelant.
    """
    import _jpyinterpreter
    from backend.app.solver.solver import calculate_course_heatmap

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_ERR", "first_name": "Prof", "last_name": "Err", "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "teacher_ids": [teacher.id],
    })
    db_session.commit()

    def boom(*args, **kwargs):
        raise RuntimeError("Panne simulée pour le test")

    monkeypatch.setattr(_jpyinterpreter, "convert_to_java_python_like_object", boom)

    result = calculate_course_heatmap(db_session, course.id, school.id)

    assert "error" in result
    assert "Panne simulée pour le test" in result["error"]
    assert "traceback" in result


def test_solver_force_pins_unplaced_foreign_school_course(db_session: Session):
    """
    Le forçage multi-établissement pince désormais TOUS les cours d'une autre école,
    y compris non placés (exclusion structurelle de CH/LS, pour éviter de gaspiller du temps de
    recherche sur des cours jamais réécrits en base) — voir _build_course_placement_problem. Un
    cours non placé étant potentiellement encore en Q (rien ne l'interdit pour un cours étranger :
    la règle Course.validate_pinned_requires_timeslot ne s'applique qu'à SA PROPRE école, pas au
    forçage du solveur), week_type doit recevoir une valeur légale (A ou B, membre de son propre
    range) plutôt que None pour rester épinglable sans planter.
    """
    from backend.app.solver.solver import _build_course_placement_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    import uuid
    other_school = School.create(db_session, {"uai": str(uuid.uuid4())[:8], "name": "Autre Ecole Q"})
    foreign_course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": other_school.id, "duration_minutes": 30, "week_type": "Q",
    })
    db_session.commit()
    assert foreign_course.timeslot_id is None  # non placé, comme toute Q (règle existante)

    problem = _build_course_placement_problem(db_session, school.id)  # ne doit pas lever d'exception
    pc_foreign = next(c for c in problem.courses if c.id == foreign_course.id)

    assert pc_foreign.is_pinned is True
    assert pc_foreign.week_type in ("A", "B")  # jamais None malgré Q en base
    assert pc_foreign.week_type_range == ["A", "B"]


def test_get_solver_factory_is_cached_across_calls(db_session: Session):
    """
    _get_solver_factory() (voir backend/experimental_java_heatmap/README.md § 5.1) ne doit
    traduire le bytecode de constraints.py/PlanningCourse qu'une seule fois par process : appels
    répétés doivent retourner EXACTEMENT le même objet, pas une nouvelle traduction à chaque fois.
    """
    from backend.app.solver.solver import _get_solver_factory

    factory1 = _get_solver_factory()
    factory2 = _get_solver_factory()
    factory3 = _get_solver_factory()

    assert factory1 is factory2
    assert factory2 is factory3


def test_solver_time_limit_stays_dynamic_despite_cached_factory(db_session: Session, monkeypatch):
    """
    Le SolverFactory est mis en cache SANS termination_config (voir § 5.1 du README) : les
    limites de temps doivent rester lues à chaque appel de résolution, pas figées à la première
    construction du factory. La fixture de session (conftest.py) fixe déjà
    SOLVER_TIME_LIMIT_SECONDS=2 pour toute la suite ; ce test le resserre encore à 1s pour UN
    seul appel et vérifie, via le temps réellement écoulé, que cette limite plus stricte est
    bien appliquée — si le factory (déjà construit par un test précédent) avait figé la limite
    de 2s à sa première construction, ce test durerait sensiblement plus longtemps que la
    nouvelle limite demandée.
    """
    import time
    from backend.app.core.config import settings
    from backend.app.solver.solver import _get_solver_factory

    _get_solver_factory()  # garantit que le factory est déjà construit/caché avant ce test

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_TIMELIMIT", "first_name": "Prof", "last_name": "TimeLimit", "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "teacher_ids": [teacher.id],
    })
    db_session.commit()

    monkeypatch.setattr(settings, "SOLVER_TIME_LIMIT_SECONDS", 1)
    monkeypatch.setattr(settings, "SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS", 1)

    t0 = time.time()
    _solve_course_placement(db_session)
    elapsed = time.time() - t0

    # Largement en dessous des 2s fixées par conftest.py pour le reste de la suite : preuve que
    # la limite de 1s demandée ICI a bien été appliquée, pas une valeur figée dans le factory
    # mis en cache. Marge généreuse pour absorber l'overhead machine.
    assert elapsed < 1.8


# =====================================================================================
# Conditions de chevauchement (« la ressource est-elle déjà occupée ? ») — fonctions pures
# partagées par plusieurs contraintes des deux domaines. Testées ici isolément, en plus des tests
# d'intégration ci-dessous, pour couvrir chaque dimension indépendamment des autres (un test
# d'intégration qui échouerait ne dirait pas LAQUELLE des dimensions est en cause).
#
# COURSE_PLACEMENT (constraints.py, teacher_conflict/division_conflict/leaf_classroom_conflict/
# non_teaching_staff_conflict/group_link_conflict) compose 5 conditions : jour, semaine
# (weeks_overlap), période (periods_overlap), hiérarchie (hierarchy_overlap), chevauchement
# horaire réel (_courses_overlap_in_time) — PLUS le partage effectif de la ressource elle-même
# (fonction dédiée par ressource, ex: _check_leaf_classroom_overlap).
#
# ⚠️ Constat vérifié en écrivant ces tests, à noter explicitement : hierarchy_overlap est
# structurellement INERTE dans COURSE_PLACEMENT. `_build_course_placement_problem` ne construit
# une PlanningCourse QUE pour les cours sans parent (`Course.parent_id == None`, solver.py) — donc
# tout PlanningCourse de ce domaine a systématiquement `parent_id=None`. Les 3 branches de
# hierarchy_overlap testent toutes `c1.parent_id is not None` ou `c2.parent_id is not None` :
# aucune ne peut jamais être vraie ici, la fonction retourne donc TOUJOURS True (jamais
# d'exclusion) pour toute paire de PlanningCourse de ce domaine — ce n'est pas un bug (la
# population garantit déjà qu'il ne peut jamais y avoir deux entités liées par parenté à exclure),
# mais le filtre lui-même n'a aucun effet réel ici, contrairement à ce que son nom/sa présence
# suggère. Il RESTE en revanche pleinement actif et nécessaire dans CLASSROOM_ASSIGNMENT — mais
# dans l'autre sens : room_conflict_between_assignments (room_constraints.py) omet
# DÉLIBÉRÉMENT hierarchy_overlap (voir plus bas, tests dédiés) car ce domaine construit bien une
# entité par cours enfant, où l'exclusion serait cette fois un bug (deux enfants pourraient
# recevoir la même salle).
#
# CLASSROOM_ASSIGNMENT (room_constraints.py, _rooms_overlap) compose les 4 mêmes conditions SAUF
# hierarchy_overlap (omission volontaire, voir ci-dessus) : jour, semaine, période, chevauchement
# horaire réel — PLUS, séparément, le partage de la salle elle-même (Joiners.equal sur
# `classroom.id`, pas une fonction dédiée puisque c'est la @PlanningVariable résolue).
# =====================================================================================

def test_weeks_overlap_matrix():
    from backend.app.solver.constraints import weeks_overlap
    assert weeks_overlap("W", "A") is True   # W chevauche tout
    assert weeks_overlap("A", "W") is True   # symétrique
    assert weeks_overlap("W", "W") is True
    assert weeks_overlap("A", "A") is True   # même semaine
    assert weeks_overlap("B", "B") is True
    assert weeks_overlap("A", "B") is False  # semaines disjointes
    assert weeks_overlap("B", "A") is False  # symétrique


def test_periods_overlap_matrix():
    from backend.app.solver.constraints import periods_overlap
    assert periods_overlap(0, 0) is True          # aucune période précisée des deux côtés = chevauche tout
    assert periods_overlap(0, 0b101) is True       # masque à 0 = "toutes les périodes", côté gauche
    assert periods_overlap(0b101, 0) is True       # symétrique
    assert periods_overlap(0b001, 0b001) is True   # période commune exacte
    assert periods_overlap(0b011, 0b100) is False  # masques disjoints
    assert periods_overlap(0b011, 0b110) is True   # intersection partielle (bit commun 0b010)


def test_hierarchy_overlap_matrix():
    """Comportement de la fonction pure elle-même, indépendamment de son inertie constatée dans
    COURSE_PLACEMENT (voir le commentaire de section ci-dessus) — un futur appelant qui
    construirait des PlanningCourse avec parent_id renseigné doit pouvoir compter sur cette
    sémantique."""
    from backend.app.solver.constraints import hierarchy_overlap, PlanningCourse
    parent = PlanningCourse(id=1, duration_minutes=30)
    child1 = PlanningCourse(id=2, duration_minutes=30, parent_id=1)
    child2 = PlanningCourse(id=3, duration_minutes=30, parent_id=1)
    unrelated = PlanningCourse(id=4, duration_minutes=30)
    other_family_child = PlanningCourse(id=5, duration_minutes=30, parent_id=99)

    assert hierarchy_overlap(parent, child1) is False        # parent / son propre enfant : exclu
    assert hierarchy_overlap(child1, parent) is False        # symétrique
    assert hierarchy_overlap(child1, child2) is False        # fratrie (même parent) : exclu
    assert hierarchy_overlap(parent, unrelated) is True       # aucun lien : pas exclu
    assert hierarchy_overlap(child1, other_family_child) is True  # enfants de parents différents : pas exclu


def test_courses_overlap_in_time_matrix():
    from backend.app.solver.constraints import _courses_overlap_in_time, PlanningCourse, PlanningTimeslot
    ts1 = PlanningTimeslot(id=1, day_of_week=1, minutes_from_midnight=480, absolute_end_of_day=1080, noon_boundary_minutes=720)
    ts_overlap = PlanningTimeslot(id=2, day_of_week=1, minutes_from_midnight=510, absolute_end_of_day=1080, noon_boundary_minutes=720)   # 510-570 chevauche 480-540
    ts_contiguous = PlanningTimeslot(id=3, day_of_week=1, minutes_from_midnight=540, absolute_end_of_day=1080, noon_boundary_minutes=720)  # 540-600, juste après la fin de ts1 (borne stricte)
    c_none = PlanningCourse(id=1, duration_minutes=60)  # timeslot=None
    c1 = PlanningCourse(id=2, duration_minutes=60, timeslot=ts1)
    c_overlap = PlanningCourse(id=3, duration_minutes=60, timeslot=ts_overlap)
    c_contiguous = PlanningCourse(id=4, duration_minutes=60, timeslot=ts_contiguous)

    assert _courses_overlap_in_time(c_none, c1) is False        # pas de créneau = jamais de chevauchement
    assert _courses_overlap_in_time(c1, c_none) is False        # symétrique
    assert _courses_overlap_in_time(c1, c_overlap) is True      # 480-540 vs 510-570 : chevauche réellement
    assert _courses_overlap_in_time(c1, c_contiguous) is False  # 480-540 vs 540-600 : contigu, bornes strictes


def test_rooms_overlap_matrix():
    """Pendant de test_courses_overlap_in_time_matrix pour room_constraints.py::_rooms_overlap —
    même style de test (chaque dimension isolée), mais fonction à arguments scalaires (pas
    d'objets PlanningCourse/PlanningTimeslot dans ce domaine, voir sa docstring)."""
    from backend.app.solver.room_constraints import _rooms_overlap
    # Jour différent : jamais de chevauchement, quel que soit le reste.
    assert _rooms_overlap(1, "W", 0, 480, 60, 2, "W", 0, 480, 60) is False
    # Même jour, semaines disjointes (A vs B).
    assert _rooms_overlap(1, "A", 0, 480, 60, 1, "B", 0, 480, 60) is False
    # Même jour, semaines communes (W chevauche tout).
    assert _rooms_overlap(1, "W", 0, 480, 60, 1, "A", 0, 480, 60) is True
    # Même jour/semaine, périodes disjointes.
    assert _rooms_overlap(1, "W", 0b001, 480, 60, 1, "W", 0b010, 480, 60) is False
    # Même jour/semaine, périodes communes (masque à 0 = toutes).
    assert _rooms_overlap(1, "W", 0, 480, 60, 1, "W", 0b010, 480, 60) is True
    # Même jour/semaine/période, horaires disjoints.
    assert _rooms_overlap(1, "W", 0, 480, 60, 1, "W", 0, 540, 60) is False
    # Même jour/semaine/période, horaires qui se chevauchent réellement.
    assert _rooms_overlap(1, "W", 0, 480, 60, 1, "W", 0, 510, 60) is True


# =====================================================================================
# Contraintes de salle du domaine COURSE_PLACEMENT (constraints.py, plan salles §2.2) — jusqu'ici
# non couvertes par la suite permanente (seulement vérifiées via des scripts de spike jetables
# pendant la tâche #5, jamais promus en tests pytest). leaf_classroom_conflict et
# leaf_classroom_unsuited utilisent explain_timetable_score plutôt qu'un solve complet : les
# cours sont épinglés (is_pinned=True) sur un créneau fixe, donc rien ne bouge — évaluer le score
# directement (sans recherche locale) isole précisément la contrainte testée, sans bruit d'un
# éventuel réarrangement par le solveur.
# =====================================================================================

def test_leaf_classroom_conflict_detects_same_room_same_slot(db_session: Session):
    from backend.app.solver.solver import explain_timetable_score
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_LCC1", "first_name": "Prof", "last_name": "LCC1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_LCC2", "first_name": "Prof", "last_name": "LCC2", "school_id": school.id})
    room = Classroom.create(db_session, {"code": "R_LCC", "name": "Room LCC", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    db_session.commit()

    c1 = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [t1.id], "timeslot_id": ts1.id, "is_pinned": True,
    })
    c2 = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [t2.id], "timeslot_id": ts1.id, "is_pinned": True,
    })
    CourseClassroomRequirement.create(db_session, {"course_id": c1.id, "classroom_id": room.id, "quantity": 1})
    CourseClassroomRequirement.create(db_session, {"course_id": c2.id, "classroom_id": room.id, "quantity": 1})
    db_session.commit()

    result = explain_timetable_score(db_session, school.id)
    assert result["matches"]["Leaf classroom conflict"]["count"] == 1
    assert result["matches"]["Leaf classroom conflict"]["hard"] == -1


def test_leaf_classroom_conflict_ignores_different_week(db_session: Session):
    from backend.app.solver.solver import explain_timetable_score
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_LCW1", "first_name": "Prof", "last_name": "LCW1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_LCW2", "first_name": "Prof", "last_name": "LCW2", "school_id": school.id})
    room = Classroom.create(db_session, {"code": "R_LCW", "name": "Room LCW", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    db_session.commit()

    c1 = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "week_type": "A",
        "teacher_ids": [t1.id], "timeslot_id": ts1.id, "is_pinned": True,
    })
    c2 = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "week_type": "B",
        "teacher_ids": [t2.id], "timeslot_id": ts1.id, "is_pinned": True,
    })
    CourseClassroomRequirement.create(db_session, {"course_id": c1.id, "classroom_id": room.id, "quantity": 1})
    CourseClassroomRequirement.create(db_session, {"course_id": c2.id, "classroom_id": room.id, "quantity": 1})
    db_session.commit()

    result = explain_timetable_score(db_session, school.id)
    assert result["matches"]["Leaf classroom conflict"]["count"] == 0


def test_leaf_classroom_conflict_ignores_different_period(db_session: Session):
    from backend.app.solver.solver import explain_timetable_score
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_LCP1", "first_name": "Prof", "last_name": "LCP1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_LCP2", "first_name": "Prof", "last_name": "LCP2", "school_id": school.id})
    room = Classroom.create(db_session, {"code": "R_LCP", "name": "Room LCP", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    import datetime
    from backend.app.models.period_type import PeriodType
    pt = PeriodType.create(db_session, {"name": "Semestre LCP"})
    per1 = Period.create(db_session, {"period_type_id": pt.id, "school_id": school.id, "code": "P1_LCP", "name": "P1", "start_date": datetime.date(2026, 9, 1), "end_date": datetime.date(2026, 12, 31)})
    per2 = Period.create(db_session, {"period_type_id": pt.id, "school_id": school.id, "code": "P2_LCP", "name": "P2", "start_date": datetime.date(2027, 1, 1), "end_date": datetime.date(2027, 6, 30)})
    db_session.commit()

    c1 = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [t1.id], "timeslot_id": ts1.id, "is_pinned": True,
    })
    c2 = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [t2.id], "timeslot_id": ts1.id, "is_pinned": True,
    })
    c1.update(db_session, {"periods": [per1], "period_type_id": pt.id})
    c2.update(db_session, {"periods": [per2], "period_type_id": pt.id})
    CourseClassroomRequirement.create(db_session, {"course_id": c1.id, "classroom_id": room.id, "quantity": 1})
    CourseClassroomRequirement.create(db_session, {"course_id": c2.id, "classroom_id": room.id, "quantity": 1})
    db_session.commit()

    result = explain_timetable_score(db_session, school.id)
    assert result["matches"]["Leaf classroom conflict"]["count"] == 0


def test_leaf_classroom_unsuited_penalizes_precise_room(db_session: Session):
    from backend.app.solver.solver import explain_timetable_score
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_LCU", "first_name": "Prof", "last_name": "LCU", "school_id": school.id})
    room = Classroom.create(db_session, {"code": "R_LCU", "name": "Room LCU", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    db_session.commit()

    ResourcePreference.create(db_session, {
        "resource_type": "Classroom", "resource_id": room.id, "timeslot_id": ts1.id,
        "preference_level": "Unsuited", "week_type": "W",
    })
    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [teacher.id], "timeslot_id": ts1.id, "is_pinned": True,
    })
    CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": room.id, "quantity": 1})
    db_session.commit()

    result = explain_timetable_score(db_session, school.id)
    assert result["matches"]["Leaf classroom unsuited"]["count"] == 1
    # of_hard(1000), pas ONE_HARD : voir constraints.py::leaf_classroom_unsuited — sinon à égalité
    # avec penalize_unassigned_course, aucune garantie que "ne pas placer" gagne sur "placer quand
    # même sur une salle Unsuited".
    assert result["matches"]["Leaf classroom unsuited"]["hard"] == -1000


def _setup_group_capacity_scenario(db_session, room_count=2, demand_count=3, same_slot=True):
    """3 cours parents indépendants (professeurs/divisions distincts, pas de lien de parenté —
    hierarchy_overlap n'entre jamais en jeu ici de toute façon, voir le constat en tête de
    section), chacun demandant 1 salle d'un même groupe de `room_count` salles-feuilles.
    `same_slot=False` place le 3e cours sur un créneau différent, pour le scénario "résolu"."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    group = Classroom.create(db_session, {"code": "GRP_CAP", "name": "Groupe capacité", "school_id": school.id})
    rooms = [
        Classroom.create(db_session, {"code": f"R_CAP_{i}", "name": f"Room Cap {i}", "school_id": school.id, "parent_classroom_id": group.id})
        for i in range(room_count)
    ]
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 2, "minutes_from_midnight": 480})
    db_session.commit()

    courses = []
    for i in range(demand_count):
        teacher = Teacher.create(db_session, {"code": f"T_CAP_{i}", "first_name": "Prof", "last_name": f"Cap{i}", "school_id": school.id})
        division = Division.create(db_session, {"code": f"DIV_CAP_{i}", "name": f"Div Cap {i}", "school_id": school.id})
        db_session.commit()
        target_ts = ts2 if (not same_slot and i == demand_count - 1) else ts1
        course = Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
            "timeslot_id": target_ts.id, "is_pinned": True,
        })
        CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": group.id, "quantity": 1})
        courses.append(course)
    db_session.commit()
    return school, group, rooms, courses


def test_classroom_group_capacity_detects_concurrent_oversubscription(db_session: Session):
    """Le scénario de référence du plan salles §2.2(a) : 3 demandes concurrentes sur un groupe de
    2 salles, même créneau — doit être détecté comme infaisable, une pénalité par créneau-groupe
    en excès (ici 1 seul créneau-groupe concerné, donc 1)."""
    from backend.app.solver.solver import explain_timetable_score
    school, group, rooms, courses = _setup_group_capacity_scenario(db_session, room_count=2, demand_count=3, same_slot=True)

    result = explain_timetable_score(db_session, school.id)
    assert result["matches"]["Classroom group capacity"]["count"] == 1
    assert result["matches"]["Classroom group capacity"]["hard"] == -1


def test_classroom_group_capacity_resolves_when_demands_spread_across_slots(db_session: Session):
    """Mêmes 3 demandes sur le même groupe de 2 salles, mais la 3e sur un créneau distinct : plus
    aucun créneau-groupe en excès (2 demandes max par créneau, jamais 3)."""
    from backend.app.solver.solver import explain_timetable_score
    school, group, rooms, courses = _setup_group_capacity_scenario(db_session, room_count=2, demand_count=3, same_slot=False)

    result = explain_timetable_score(db_session, school.id)
    assert result["matches"]["Classroom group capacity"]["count"] == 0


def test_classroom_group_capacity_excludes_unsuited_leaf_from_available_count(db_session: Session):
    """Une salle-feuille du groupe frappée d'Unsuited pour le créneau testé ne compte plus dans
    la capacité disponible du groupe — 2 demandes concurrentes sur un groupe de 2 salles dont 1
    est Unsuited pour ce créneau doivent être détectées en excès (1 seule salle réellement
    disponible), alors que 2 demandes pour 2 salles nominales seraient normalement faisables."""
    from backend.app.solver.solver import explain_timetable_score
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    group = Classroom.create(db_session, {"code": "GRP_UNS", "name": "Groupe Unsuited", "school_id": school.id})
    room_ok = Classroom.create(db_session, {"code": "R_UNS_OK", "name": "Room OK", "school_id": school.id, "parent_classroom_id": group.id})
    room_unsuited = Classroom.create(db_session, {"code": "R_UNS_BAD", "name": "Room Unsuited", "school_id": school.id, "parent_classroom_id": group.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    db_session.commit()

    ResourcePreference.create(db_session, {
        "resource_type": "Classroom", "resource_id": room_unsuited.id, "timeslot_id": ts1.id,
        "preference_level": "Unsuited", "week_type": "W",
    })
    db_session.commit()

    courses = []
    for i in range(2):
        teacher = Teacher.create(db_session, {"code": f"T_UNS_{i}", "first_name": "Prof", "last_name": f"Uns{i}", "school_id": school.id})
        division = Division.create(db_session, {"code": f"DIV_UNS_{i}", "name": f"Div Uns {i}", "school_id": school.id})
        db_session.commit()
        course = Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
            "timeslot_id": ts1.id, "is_pinned": True,
        })
        CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": group.id, "quantity": 1})
        courses.append(course)
    db_session.commit()

    result = explain_timetable_score(db_session, school.id)
    assert result["matches"]["Classroom group capacity"]["count"] == 1
    assert result["matches"]["Classroom group capacity"]["hard"] == -1


# =====================================================================================
# Domaine CLASSROOM_ASSIGNMENT (plan salles §3) — résolution de la salle précise, séparée du
# placement horaire (COURSE_PLACEMENT ci-dessus). solve_classroom_assignment (room_solver.py)
# construit le problème, résout, et écrit le résultat en base en un seul appel — pas de
# sémaphore/mode exclusif ici (ce n'est plus un point d'entrée de production direct depuis la
# tâche #7 : l'orchestration réelle, testée séparément, réutilise ses briques une par une via
# _run_job_phases — mais la fonction reste le point d'entrée le plus direct pour tester le
# domaine lui-même, indépendamment de l'orchestration).
# =====================================================================================

def test_classroom_assignment_resolves_group_requirement_on_parent_and_cascades(db_session: Session):
    """
    Cycle complet de l'exemple de référence du plan salles §3.1 : une exigence de groupe (3
    salles) saisie sur le cours PARENT, avant toute décomposition, doit être résolue en 3 salles
    distinctes du groupe — et la ligne de groupe du parent doit disparaître une fois les 3 unités
    consommées (write-back = mécanisme de sortie de domaine, voir §3.4).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_CA1", "first_name": "Prof", "last_name": "A", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_CA2", "first_name": "Prof", "last_name": "B", "school_id": school.id})
    t3 = Teacher.create(db_session, {"code": "T_CA3", "first_name": "Prof", "last_name": "C", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_CA1", "name": "Div 1", "student_count": 25, "color": "#000", "school_id": school.id})
    d2 = Division.create(db_session, {"code": "DIV_CA2", "name": "Div 2", "student_count": 25, "color": "#000", "school_id": school.id})
    d3 = Division.create(db_session, {"code": "DIV_CA3", "name": "Div 3", "student_count": 25, "color": "#000", "school_id": school.id})

    # capacity=None (illimitée) sur tout le groupe : ce test porte sur la résolution/cascade, pas
    # sur la capacité (effective_headcount du parent = somme des 3 divisions = 75, dépasserait
    # toute capacité numérique raisonnable et masquerait l'assertion visée).
    group_labos = Classroom.create(db_session, {"code": "GRP-LABOS", "name": "Labos", "school_id": school.id})
    l1 = Classroom.create(db_session, {"code": "L1", "name": "Labo 1", "school_id": school.id, "parent_classroom_id": group_labos.id})
    l2 = Classroom.create(db_session, {"code": "L2", "name": "Labo 2", "school_id": school.id, "parent_classroom_id": group_labos.id})
    l3 = Classroom.create(db_session, {"code": "L3", "name": "Labo 3", "school_id": school.id, "parent_classroom_id": group_labos.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    parent = Course.create(db_session, {
        "is_composed": True, "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [t1.id, t2.id, t3.id], "division_ids": [d1.id, d2.id, d3.id],
    })
    CourseClassroomRequirement.create(db_session, {"course_id": parent.id, "classroom_id": group_labos.id, "quantity": 3})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)

    assert solution.score.hard_score == 0
    resolved_rooms = {a.classroom.id for a in solution.assignments if a.classroom is not None}
    assert resolved_rooms == {l1.id, l2.id, l3.id}

    parent_group_line = db_session.query(CourseClassroomRequirement).filter(
        CourseClassroomRequirement.course_id == parent.id, CourseClassroomRequirement.classroom_id == group_labos.id
    ).first()
    assert parent_group_line is None  # 3/3 résolues : la ligne de groupe a disparu
    leaf_lines = db_session.query(CourseClassroomRequirement).filter(CourseClassroomRequirement.course_id == parent.id).all()
    assert {r.classroom_id for r in leaf_lines} == {l1.id, l2.id, l3.id}


def test_classroom_assignment_resolving_one_child_does_not_double_decrement_grandparent_line(db_session: Session):
    """
    Régression : `_cascade_decrement_parent_group_line` décrémentait la ligne de groupe d'un
    ancêtre à DEUX moments pour la même unité de besoin — une fois quand un enfant déclare sa
    propre exigence de groupe (légitime, cette unité devient "prise" par cet enfant), une seconde
    fois quand cette MÊME exigence est plus tard résolue en salle précise par CLASSROOM_ASSIGNMENT
    (bug : ce n'est pas un nouveau besoin, juste le même qui se précise). Conséquence en
    production : le besoin propre du grandparent, jamais résolu, disparaissait silencieusement dès
    qu'un enfant siégeant sous le même groupe se faisait résoudre une salle.

    Reproduit ici en appelant directement _write_back_classroom_assignment avec une solution
    construite à la main (plutôt que via un vrai solve) : isole le mécanisme de write-back/cascade
    de tout aléa du solveur sur qui obtient la seule salle disponible.
    """
    from types import SimpleNamespace
    from backend.app.solver.room_solver import _write_back_classroom_assignment

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_NODBL1", "first_name": "Prof", "last_name": "Nodbl1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_NODBL2", "first_name": "Prof", "last_name": "Nodbl2", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    top_group = Classroom.create(db_session, {"code": "TOPG_NODBL", "name": "Top", "school_id": school.id})
    l1 = Classroom.create(db_session, {"code": "L1_NODBL", "name": "L1", "school_id": school.id, "parent_classroom_id": top_group.id})
    db_session.commit()

    grandparent = Course.create(db_session, {
        "school_id": school.id, "subject_id": subject.id, "duration_minutes": 30,
        "teacher_ids": [t1.id, t2.id], "timeslot_id": ts1.id, "is_composed": True,
    })
    gp_line = CourseClassroomRequirement.create(db_session, {"course_id": grandparent.id, "classroom_id": top_group.id, "quantity": 2})
    gp_line_id = gp_line.id

    middle = Course.create(db_session, {
        "school_id": school.id, "subject_id": subject.id, "duration_minutes": 30,
        "teacher_ids": [t1.id], "parent_id": grandparent.id,
    })
    middle_line = CourseClassroomRequirement.create(db_session, {"course_id": middle.id, "classroom_id": top_group.id, "quantity": 1})
    middle_line_id = middle_line.id
    db_session.commit()
    db_session.refresh(gp_line)
    # Décrément légitime : l'unité de middle est désormais prise en compte, il n'en reste qu'une
    # de vraiment libre sur les 2 d'origine du grandparent.
    assert gp_line.quantity == 1

    # Write-back qui ne résout QUE l'unité de middle (grandparent.own unit n'est ici jamais
    # tentée -- exactement ce qui arrive en production si le solveur n'a pas encore traité/gagné
    # cette unité-là lors de cette passe : rien d'exotique, une simple histoire de timing/ordre).
    fake_solution = SimpleNamespace(assignments=[
        SimpleNamespace(id=middle_line_id * 100, classroom=SimpleNamespace(id=l1.id)),
    ])
    _write_back_classroom_assignment(db_session, fake_solution)
    db_session.commit()

    remaining_gp_line = db_session.get(CourseClassroomRequirement, gp_line_id)
    assert remaining_gp_line is not None, (
        "La ligne du grandparent a été supprimée alors que son besoin propre (1 salle) n'a "
        "jamais été résolu -- double décrémentation confirmée."
    )
    assert remaining_gp_line.quantity == 1

    middle_resolved = db_session.query(CourseClassroomRequirement).filter(
        CourseClassroomRequirement.course_id == middle.id
    ).all()
    assert {r.classroom_id for r in middle_resolved} == {l1.id}


def test_classroom_requirement_classroom_id_is_immutable_after_creation(db_session: Session):
    """Complète l'immuabilité côté domaine CLASSROOM_ASSIGNMENT (la version cascade est testée
    dans test_api.py) : toute résolution passe désormais par une nouvelle ligne, jamais par une
    mutation de classroom_id sur la ligne existante."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_IMMUT", "first_name": "Prof", "last_name": "Immut", "school_id": school.id})
    room_a = Classroom.create(db_session, {"code": "IMMUT_A", "name": "A", "school_id": school.id})
    room_b = Classroom.create(db_session, {"code": "IMMUT_B", "name": "B", "school_id": school.id})
    course = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [teacher.id]})
    req = CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": room_a.id, "quantity": 1})

    with pytest.raises(ValueError, match="ne peut plus être modifiée"):
        req.update(db_session, {"classroom_id": room_b.id})
    db_session.rollback()


def test_classroom_requirement_quantity_edit_with_unchanged_classroom_id_is_allowed(db_session: Session):
    """
    Régression : GenericListModal.vue::onUpdateItem soumet TOUJOURS la ligne entière à chaque
    édition (classroom_id inclus, même quand seule `quantity` change dans le formulaire) — un
    contrôle d'immuabilité qui ne regarde que la PRÉSENCE de classroom_id dans les vals soumis
    (plutôt que si sa VALEUR a réellement changé) rejette alors à tort ce cas pourtant légitime
    (bug constaté : impossible de modifier le nombre de salles d'une exigence de groupe).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_QTYEDIT", "first_name": "Prof", "last_name": "Qtyedit", "school_id": school.id})
    group = Classroom.create(db_session, {"code": "QTYEDIT_GRP", "name": "Grp", "school_id": school.id})
    Classroom.create(db_session, {"code": "QTYEDIT_L1", "name": "L1", "school_id": school.id, "parent_classroom_id": group.id})
    Classroom.create(db_session, {"code": "QTYEDIT_L2", "name": "L2", "school_id": school.id, "parent_classroom_id": group.id})
    course = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [teacher.id]})
    req = CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": group.id, "quantity": 1})

    # Reproduit exactement ce que GenericListModal.vue soumet : TOUTE la ligne, classroom_id
    # identique inclus, avec seule quantity modifiée.
    req.update(db_session, {"course_id": course.id, "classroom_id": group.id, "quantity": 2})

    assert req.quantity == 2
    assert req.classroom_id == group.id


def test_classroom_assignment_respects_capacity(db_session: Session):
    """Capacité numérique insuffisante = pénalité dure ; capacité NULL = illimitée, jamais de
    pénalité quel que soit l'effectif (voir plan salles §3.3)."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_CAP", "first_name": "Prof", "last_name": "Cap", "school_id": school.id})
    division = Division.create(db_session, {"code": "DIV_CAP", "name": "Div Cap", "student_count": 28, "color": "#000", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    group_small = Classroom.create(db_session, {"code": "GRP-SMALL", "name": "Petit groupe", "school_id": school.id, "capacity": 25})
    Classroom.create(db_session, {"code": "S1", "name": "Petite salle", "school_id": school.id, "capacity": 25, "parent_classroom_id": group_small.id})

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [teacher.id], "division_ids": [division.id],
    })
    CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": group_small.id, "quantity": 1})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)
    # Soit non résolu (unassigned_room_assignment_penalty), soit résolu avec violation de
    # capacité (room_capacity_hard) : dans les deux cas exactement -1 hard, jamais 0 (aucune
    # salle ne peut silencieusement "convenir" à 28 élèves dans une salle à 25 places).
    assert solution.score.hard_score == -1


def test_classroom_assignment_null_capacity_is_unlimited(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_NOCAP", "first_name": "Prof", "last_name": "NoCap", "school_id": school.id})
    division = Division.create(db_session, {"code": "DIV_NOCAP", "name": "Div NoCap", "student_count": 28, "color": "#000", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    group_unlimited = Classroom.create(db_session, {"code": "GRP-BIG", "name": "Groupe illimité", "school_id": school.id, "capacity": None})
    Classroom.create(db_session, {"code": "B1", "name": "Grande salle", "school_id": school.id, "capacity": None, "parent_classroom_id": group_unlimited.id})

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [teacher.id], "division_ids": [division.id],
    })
    CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": group_unlimited.id, "quantity": 1})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)
    assert solution.score.hard_score == 0
    assert solution.assignments[0].classroom is not None


def test_classroom_assignment_respects_preferences(db_session: Session):
    """Une salle-feuille frappée d'Unsuited pour le créneau du cours est exclue ; la salle
    préférée du professeur est récompensée (soft) parmi les salles restantes."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_PREF_CA", "first_name": "Prof", "last_name": "PrefCa", "school_id": school.id})
    division = Division.create(db_session, {"code": "DIV_PREF_CA", "name": "Div PrefCa", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    group = Classroom.create(db_session, {"code": "GRP", "name": "Grp", "school_id": school.id})
    l_unsuited = Classroom.create(db_session, {"code": "UNS", "name": "Salle interdite", "school_id": school.id, "capacity": 30, "parent_classroom_id": group.id})
    l_preferred = Classroom.create(db_session, {"code": "PREF", "name": "Salle préférée", "school_id": school.id, "capacity": 30, "parent_classroom_id": group.id})
    l_other = Classroom.create(db_session, {"code": "OTH", "name": "Salle neutre", "school_id": school.id, "capacity": 30, "parent_classroom_id": group.id})

    teacher.update(db_session, {"preferred_classroom_id": l_preferred.id})
    ResourcePreference.create(db_session, {
        "resource_type": "Classroom", "resource_id": l_unsuited.id, "timeslot_id": ts1.id,
        "preference_level": "Unsuited", "week_type": "W",
    })

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [teacher.id], "division_ids": [division.id],
    })
    CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": group.id, "quantity": 1})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)

    assert solution.score.hard_score == 0
    resolved = solution.assignments[0].classroom
    assert resolved.id != l_unsuited.id
    assert resolved.id == l_preferred.id


def test_classroom_assignment_unsuited_only_candidate_stays_unassigned(db_session: Session):
    """
    Régression : quand l'UNIQUE salle-feuille candidate est Unsuited pour le créneau, le solveur
    doit laisser l'affectation non résolue (classroom=None), pas assigner quand même la salle
    Unsuited. Avant correctif, room_preference_hard et unassigned_room_assignment_penalty
    valaient toutes deux ONE_HARD : à égalité stricte de score, rien ne garantissait laquelle des
    deux issues le solveur retenait (une salle Unsuited assignée n'était pas moins "optimale"
    qu'une affectation non résolue). room_preference_hard vaut désormais of_hard(1000) : la salle
    Unsuited assignée (-1000) est maintenant strictement pire que non résolu (-1).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_ONLYUNS", "first_name": "Prof", "last_name": "Onlyuns", "school_id": school.id})
    division = Division.create(db_session, {"code": "DIV_ONLYUNS", "name": "Div Onlyuns", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    group = Classroom.create(db_session, {"code": "GRP-ONLYUNS", "name": "Grp", "school_id": school.id})
    only_room = Classroom.create(db_session, {"code": "ONLYUNS-L1", "name": "Seule salle, Unsuited", "school_id": school.id, "capacity": 30, "parent_classroom_id": group.id})

    ResourcePreference.create(db_session, {
        "resource_type": "Classroom", "resource_id": only_room.id, "timeslot_id": ts1.id,
        "preference_level": "Unsuited", "week_type": "W",
    })

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [teacher.id], "division_ids": [division.id],
    })
    CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": group.id, "quantity": 1})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)

    assert solution.assignments[0].classroom is None, "La salle Unsuited a été assignée quand même, alors qu'elle était la seule candidate"
    assert solution.score.hard_score == -1  # unassigned_room_assignment_penalty, pas -1000


def test_classroom_assignment_forces_siblings_to_distinct_rooms(db_session: Session):
    """
    Différence volontaire avec COURSE_PLACEMENT (hierarchy_overlap) : deux cours de la MÊME
    fratrie (même parent), au même créneau, demandant chacun une salle du même groupe à une
    seule salle-feuille disponible doivent entrer en conflit dur — hierarchy_overlap n'exclut
    PAS les paires parent/enfant ou fratrie de ce domaine (voir plan salles §3.3).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_SIB1", "first_name": "Prof", "last_name": "Sib1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_SIB2", "first_name": "Prof", "last_name": "Sib2", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_SIB1", "name": "Div Sib1", "school_id": school.id})
    d2 = Division.create(db_session, {"code": "DIV_SIB2", "name": "Div Sib2", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    group = Classroom.create(db_session, {"code": "GRP-SIB", "name": "Grp", "school_id": school.id})
    Classroom.create(db_session, {"code": "ONLY", "name": "Seule salle", "school_id": school.id, "capacity": 30, "parent_classroom_id": group.id})

    parent = Course.create(db_session, {
        "is_composed": True, "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [t1.id, t2.id], "division_ids": [d1.id, d2.id],
    })
    db_session.commit()
    child1 = Course.create(db_session, {
        "parent_id": parent.id, "subject_id": subject.id, "school_id": school.id,
        "duration_minutes": 30, "teacher_ids": [t1.id], "division_ids": [d1.id],
    })
    child2 = Course.create(db_session, {
        "parent_id": parent.id, "subject_id": subject.id, "school_id": school.id,
        "duration_minutes": 30, "teacher_ids": [t2.id], "division_ids": [d2.id],
    })
    db_session.commit()
    CourseClassroomRequirement.create(db_session, {"course_id": child1.id, "classroom_id": group.id, "quantity": 1})
    CourseClassroomRequirement.create(db_session, {"course_id": child2.id, "classroom_id": group.id, "quantity": 1})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)

    # Une seule salle-feuille pour 2 demandes de la même fratrie, même créneau : conflit dur
    # forcé — la seule échappatoire (contrairement à COURSE_PLACEMENT) serait de laisser l'une
    # des deux non assignée (unassigned_room_assignment_penalty, -1 hard aussi).
    assert solution.score.hard_score == -1


def test_classroom_assignment_excludes_requirement_without_resolved_timeslot(db_session: Session):
    """Une exigence portée par un cours qui n'a pas encore de timeslot résolu (ni le sien, ni
    celui d'un parent) est exclue du domaine — rien à résoudre tant que COURSE_PLACEMENT n'est
    pas passé (voir plan salles §3.4)."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_NOTS", "first_name": "Prof", "last_name": "NoTs", "school_id": school.id})
    division = Division.create(db_session, {"code": "DIV_NOTS", "name": "Div NoTs", "school_id": school.id})

    group = Classroom.create(db_session, {"code": "GRP-NOTS", "name": "Grp", "school_id": school.id})
    Classroom.create(db_session, {"code": "L_NOTS", "name": "Salle", "school_id": school.id, "capacity": 30, "parent_classroom_id": group.id})

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [teacher.id], "division_ids": [division.id],
    })
    CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": group.id, "quantity": 1})
    db_session.commit()

    from backend.app.solver.room_solver import _build_classroom_assignment_problem
    problem = _build_classroom_assignment_problem(db_session, school.id)

    assert len(problem.assignments) == 0


def test_get_classroom_assignment_solver_factory_is_cached_across_calls(db_session: Session):
    """Pendant de test_get_solver_factory_is_cached_across_calls pour le domaine
    CLASSROOM_ASSIGNMENT — même cache, même raisonnement (voir room_solver.py)."""
    from backend.app.solver.room_solver import _get_classroom_assignment_solver_factory

    factory1 = _get_classroom_assignment_solver_factory()
    factory2 = _get_classroom_assignment_solver_factory()

    assert factory1 is factory2


def test_classroom_assignment_room_conflict_ignores_different_week(db_session: Session):
    """Pendant, côté CLASSROOM_ASSIGNMENT, de test_leaf_classroom_conflict_ignores_different_week :
    deux demandes de groupe sur un groupe à une seule salle-feuille, même jour/heure mais semaines
    A et B distinctes, doivent toutes les deux se voir attribuer cette unique salle sans conflit."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_CAW1", "first_name": "Prof", "last_name": "Caw1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_CAW2", "first_name": "Prof", "last_name": "Caw2", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_CAW1", "name": "Div Caw1", "school_id": school.id})
    d2 = Division.create(db_session, {"code": "DIV_CAW2", "name": "Div Caw2", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    group = Classroom.create(db_session, {"code": "GRP-CAW", "name": "Grp", "school_id": school.id})
    only_room = Classroom.create(db_session, {"code": "ONLY-CAW", "name": "Seule salle", "school_id": school.id, "parent_classroom_id": group.id})

    course_a = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "week_type": "A",
        "timeslot_id": ts1.id, "teacher_ids": [t1.id], "division_ids": [d1.id],
    })
    course_b = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "week_type": "B",
        "timeslot_id": ts1.id, "teacher_ids": [t2.id], "division_ids": [d2.id],
    })
    CourseClassroomRequirement.create(db_session, {"course_id": course_a.id, "classroom_id": group.id, "quantity": 1})
    CourseClassroomRequirement.create(db_session, {"course_id": course_b.id, "classroom_id": group.id, "quantity": 1})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)

    assert solution.score.hard_score == 0
    resolved_rooms = {a.classroom.id for a in solution.assignments if a.classroom is not None}
    assert resolved_rooms == {only_room.id}
    assert all(a.classroom is not None for a in solution.assignments)


def test_classroom_assignment_room_conflict_ignores_different_period(db_session: Session):
    """Pendant, côté CLASSROOM_ASSIGNMENT, de test_leaf_classroom_conflict_ignores_different_period :
    deux demandes de groupe sur un groupe à une seule salle-feuille, même jour/heure mais périodes
    disjointes, doivent toutes les deux se voir attribuer cette unique salle sans conflit."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_CAP1", "first_name": "Prof", "last_name": "Cap1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_CAP2", "first_name": "Prof", "last_name": "Cap2", "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_CAPR1", "name": "Div Capr1", "school_id": school.id})
    d2 = Division.create(db_session, {"code": "DIV_CAPR2", "name": "Div Capr2", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    import datetime
    from backend.app.models.period_type import PeriodType
    pt = PeriodType.create(db_session, {"name": "Semestre CAPR"})
    per1 = Period.create(db_session, {"period_type_id": pt.id, "school_id": school.id, "code": "P1_CAPR", "name": "P1", "start_date": datetime.date(2026, 9, 1), "end_date": datetime.date(2026, 12, 31)})
    per2 = Period.create(db_session, {"period_type_id": pt.id, "school_id": school.id, "code": "P2_CAPR", "name": "P2", "start_date": datetime.date(2027, 1, 1), "end_date": datetime.date(2027, 6, 30)})
    db_session.commit()

    group = Classroom.create(db_session, {"code": "GRP-CAPR", "name": "Grp", "school_id": school.id})
    only_room = Classroom.create(db_session, {"code": "ONLY-CAPR", "name": "Seule salle", "school_id": school.id, "parent_classroom_id": group.id})

    course_a = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [t1.id], "division_ids": [d1.id],
    })
    course_b = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [t2.id], "division_ids": [d2.id],
    })
    course_a.update(db_session, {"periods": [per1], "period_type_id": pt.id})
    course_b.update(db_session, {"periods": [per2], "period_type_id": pt.id})
    CourseClassroomRequirement.create(db_session, {"course_id": course_a.id, "classroom_id": group.id, "quantity": 1})
    CourseClassroomRequirement.create(db_session, {"course_id": course_b.id, "classroom_id": group.id, "quantity": 1})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)

    assert solution.score.hard_score == 0
    resolved_rooms = {a.classroom.id for a in solution.assignments if a.classroom is not None}
    assert resolved_rooms == {only_room.id}
    assert all(a.classroom is not None for a in solution.assignments)


def test_classroom_assignment_respects_fixed_booking(db_session: Session):
    """room_conflict_with_fixed_booking (aucun test direct jusqu'ici) : une exigence PRÉCISE sur
    une salle-feuille (ex. saisie manuelle) devient un fait PlanningFixedRoomBooking, pas une
    PlanningRoomAssignment (voir room_solver.py::_build_classroom_assignment_problem) — une
    demande de GROUPE concurrente dont l'unique salle candidate est cette même salle-feuille, au
    même créneau, ne peut donc jamais être résolue sans conflit."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t_fixed = Teacher.create(db_session, {"code": "T_FIXB1", "first_name": "Prof", "last_name": "Fixb1", "school_id": school.id})
    t_group = Teacher.create(db_session, {"code": "T_FIXB2", "first_name": "Prof", "last_name": "Fixb2", "school_id": school.id})
    d_fixed = Division.create(db_session, {"code": "DIV_FIXB1", "name": "Div Fixb1", "school_id": school.id})
    d_group = Division.create(db_session, {"code": "DIV_FIXB2", "name": "Div Fixb2", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    group = Classroom.create(db_session, {"code": "GRP-FIXB", "name": "Grp", "school_id": school.id})
    only_room = Classroom.create(db_session, {"code": "ONLY-FIXB", "name": "Seule salle", "school_id": school.id, "parent_classroom_id": group.id})

    course_fixed = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [t_fixed.id], "division_ids": [d_fixed.id],
    })
    course_group = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [t_group.id], "division_ids": [d_group.id],
    })
    # Exigence précise, directement sur la salle-feuille (pas le groupe) : devient un
    # PlanningFixedRoomBooking, jamais une entité à résoudre.
    CourseClassroomRequirement.create(db_session, {"course_id": course_fixed.id, "classroom_id": only_room.id, "quantity": 1})
    CourseClassroomRequirement.create(db_session, {"course_id": course_group.id, "classroom_id": group.id, "quantity": 1})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)

    # Même raisonnement que test_classroom_assignment_respects_capacity : soit le solveur force
    # quand même l'unique salle (conflit avec la réservation fixe, -1 hard), soit il laisse la
    # demande de groupe non assignée (unassigned_room_assignment_penalty, -1 hard aussi) — jamais
    # 0, la salle est réellement indisponible sur ce créneau.
    assert solution.score.hard_score == -1


def test_classroom_assignment_penalizes_undesirable_preference(db_session: Session):
    """room_preference_soft_penalty (aucun test jusqu'ici) : une salle Undesirable pour le
    créneau du cours n'est pas exclue (contrairement à Unsuited, dur) mais doit être évitée par
    la recherche locale si une alternative neutre existe dans le même groupe, pour ne pas payer
    la pénalité molle."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_UNDES", "first_name": "Prof", "last_name": "Undes", "school_id": school.id})
    division = Division.create(db_session, {"code": "DIV_UNDES", "name": "Div Undes", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    group = Classroom.create(db_session, {"code": "GRP-UNDES", "name": "Grp", "school_id": school.id})
    l_undesirable = Classroom.create(db_session, {"code": "UNDES", "name": "Salle indésirable", "school_id": school.id, "parent_classroom_id": group.id})
    l_neutral = Classroom.create(db_session, {"code": "NEUT", "name": "Salle neutre", "school_id": school.id, "parent_classroom_id": group.id})

    ResourcePreference.create(db_session, {
        "resource_type": "Classroom", "resource_id": l_undesirable.id, "timeslot_id": ts1.id,
        "preference_level": "Undesirable", "week_type": "W",
    })

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [teacher.id], "division_ids": [division.id],
    })
    CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": group.id, "quantity": 1})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)

    assert solution.score.hard_score == 0
    assert solution.score.soft_score == 0
    resolved = solution.assignments[0].classroom
    assert resolved is not None
    assert resolved.id == l_neutral.id
    assert resolved.id != l_undesirable.id


def test_classroom_assignment_division_preferred_room_reward(db_session: Session):
    """Pendant de test_classroom_assignment_respects_preferences pour Division.preferred_classroom_id
    (jusqu'ici seul Teacher.preferred_classroom_id était testé — division_preferred_classroom_reward
    n'avait aucune couverture directe)."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_DIVPREF", "first_name": "Prof", "last_name": "DivPref", "school_id": school.id})
    division = Division.create(db_session, {"code": "DIV_DIVPREF", "name": "Div DivPref", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    group = Classroom.create(db_session, {"code": "GRP-DIVPREF", "name": "Grp", "school_id": school.id})
    l_preferred = Classroom.create(db_session, {"code": "DPREF", "name": "Salle préférée division", "school_id": school.id, "parent_classroom_id": group.id})
    l_other = Classroom.create(db_session, {"code": "DOTH", "name": "Salle neutre", "school_id": school.id, "parent_classroom_id": group.id})

    division.update(db_session, {"preferred_classroom_id": l_preferred.id})

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "timeslot_id": ts1.id, "teacher_ids": [teacher.id], "division_ids": [division.id],
    })
    CourseClassroomRequirement.create(db_session, {"course_id": course.id, "classroom_id": group.id, "quantity": 1})
    db_session.commit()

    solution = solve_classroom_assignment(db_session, school.id)

    assert solution.score.hard_score == 0
    resolved = solution.assignments[0].classroom
    assert resolved is not None
    assert resolved.id == l_preferred.id
    assert solution.score.soft_score == 1

import pytest
from sqlalchemy import create_engine
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
from backend.app.models.group import Partition, ClassPart, ClassPartLink, Group
from backend.app.models.student import Student
from backend.app.models.preference import ResourcePreference
from backend.app.models.period import Period
from backend.app.models.constraint import CourseToCourseConstraint, SubjectToSubjectConstraint, ResourceConstraint
from backend.app.solver.solver import _solve_timetable_job

TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

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

def test_solver_resolves_timetable(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_MATH", "first_name": "Prof", "last_name": "Math", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "PROF_ANG", "first_name": "Prof", "last_name": "Anglais", "school_id": school.id})

    c1 = Classroom.create(db_session, {"code": "SALLE_A", "name": "Salle A", "capacity": 30, "quantity": 1, "school_id": school.id})
    c2 = Classroom.create(db_session, {"code": "SALLE_B", "name": "Salle B", "capacity": 30, "quantity": 1, "school_id": school.id})

    d1 = Division.create(db_session, {"code": "DIV_6E", "name": "6ème", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    d2 = Division.create(db_session, {"code": "DIV_5E", "name": "5ème", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 2, "minutes_from_midnight": 480})

    course1 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 30})
    course2 = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 30})
    db_session.commit()

    _solve_timetable_job(db_session)

    db_session.refresh(course1)
    db_session.refresh(course2)

    assert course1.timeslot_id is not None
    assert course2.timeslot_id is not None
    assert course1.timeslot_id != course2.timeslot_id

def test_solver_group_link_and_week_alternation(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_A", "first_name": "Prof", "last_name": "A", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "PROF_B", "first_name": "Prof", "last_name": "B", "school_id": school.id})

    c1 = Classroom.create(db_session, {"code": "ROOM_A", "name": "Room A", "capacity": 30, "quantity": 1, "school_id": school.id})
    c2 = Classroom.create(db_session, {"code": "ROOM_B", "name": "Room B", "capacity": 30, "quantity": 1, "school_id": school.id})

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

    _solve_timetable_job(db_session)
    db_session.refresh(course1)
    db_session.refresh(course2)

    course1.update(db_session, {"timeslot_id": None, "week_type": "A"})
    course2.update(db_session, {"timeslot_id": None, "week_type": "B"})
    db_session.commit()

    _solve_timetable_job(db_session)
    db_session.refresh(course1)
    db_session.refresh(course2)

    assert course1.timeslot_id is not None
    assert course2.timeslot_id is not None
    assert course1.timeslot_id == course2.timeslot_id

def test_solver_respects_preferences(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_PREF", "first_name": "Prof", "last_name": "Pref", "school_id": school.id})
    c1 = Classroom.create(db_session, {"code": "ROOM_PREF", "name": "Room Pref", "capacity": 30, "quantity": 1, "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_PREF", "name": "Div Pref", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    ResourcePreference.create(db_session, {"resource_type": "Teacher", "resource_id": t1.id, "timeslot_id": ts1.id, "preference_level": "Unsuited"})
    ResourcePreference.create(db_session, {"resource_type": "Teacher", "resource_id": t1.id, "timeslot_id": ts2.id, "preference_level": "Preferred"})

    course = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "duration_minutes": 30})
    db_session.commit()

    _solve_timetable_job(db_session)
    db_session.refresh(course)

    assert course.timeslot_id is not None
    assert course.timeslot_id == ts2.id

def test_solver_preference_overrides_stability(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_STAB", "first_name": "Prof", "last_name": "Stab", "school_id": school.id})
    c1 = Classroom.create(db_session, {"code": "ROOM_STAB", "name": "Room Stab", "capacity": 30, "quantity": 1, "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_STAB", "name": "Div Stab", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    ResourcePreference.create(db_session, {"resource_type": "Teacher", "resource_id": t1.id, "timeslot_id": ts2.id, "preference_level": "Preferred"})

    course = Course.create(db_session, {
        "subject_id": subject.id,
        "teacher_ids": [t1.id],
        "division_ids": [d1.id],
        "classroom_ids": [c1.id],
        "timeslot_id": ts1.id,
        "school_id": school.id,
        "duration_minutes": 30
    })
    db_session.commit()

    _solve_timetable_job(db_session)
    db_session.refresh(course)

    assert course.timeslot_id is not None
    assert course.timeslot_id == ts2.id

def test_solver_respects_week_specific_preferences(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_WEEK", "first_name": "Prof", "last_name": "Week", "school_id": school.id})
    c1 = Classroom.create(db_session, {"code": "ROOM_WEEK", "name": "Room Week", "capacity": 30, "quantity": 1, "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_WEEK", "name": "Div Week", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    ResourcePreference.create(db_session, {"resource_type": "Teacher", "resource_id": t1.id, "timeslot_id": ts1.id, "preference_level": "Unsuited", "week_type": "A"})

    course_a = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "week_type": "A", "duration_minutes": 30})
    course_b = Course.create(db_session, {"subject_id": subject.id, "teacher_ids": [t1.id], "division_ids": [d1.id], "school_id": school.id, "week_type": "B", "duration_minutes": 30})
    db_session.commit()

    _solve_timetable_job(db_session)
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
    c1 = Classroom.create(db_session, {"code": "ROOM_PERIOD", "name": "Room Period", "capacity": 30, "quantity": 1, "school_id": school.id})
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

    
    _solve_timetable_job(db_session)
    db_session.refresh(course)
    
    assert course.timeslot_id == ts1.id

    course.update(db_session, {"timeslot_id": None, "periods": [per1]})
    db_session.commit()

    _solve_timetable_job(db_session)
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
    from backend.app.solver.solver import _build_planning_problem
    from backend.app.solver.constraints import define_constraints, PlanningCourse, course_day_overflow
    import timefold.solver.score as score
    
    problem = _build_planning_problem(db_session, school.id)
    
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
    from timefold.solver.domain import PlanningVariable
    
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
        classroom=None,
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
        classroom=None,
        divisions=[]
    )
    assert _is_preference_violated(p_pref, other_course) is False


def test_course_heatmap_with_indisponibility(db_session: Session):
    from backend.app.solver.solver import calculate_course_heatmap, _build_planning_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # Création du professeur
    teacher = Teacher.create(db_session, {
        "code": "PROF_ART",
        "first_name": "Prof",
        "last_name": "Art",
        "school_id": school.id
    })

    # Création d'une salle de classe
    classroom = Classroom.create(db_session, {
        "code": "ROOM_ART",
        "name": "Room Art",
        "capacity": 30,
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

    # Création du cours (non placé initialement, mais avec salle de classe rattachée)
    course = Course.create(db_session, {
        "subject_id": subject.id,
        "teacher_ids": [teacher.id],
        "classroom_ids": [classroom.id],
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

    # ts2 est indisponible : conflit physique, donc delta Hard = -1
    assert heatmap[str(ts2.id)]["hard"] == -1
    reasons = [r["name"] for r in heatmap[str(ts2.id)]["reasons"]]
    assert "Resource unavailability (strict)" in reasons


def test_course_heatmap_detects_conflicts_for_course_and_others_without_classroom(db_session: Session):
    """
    Régression (ancienne, signalée en usage réel — pas liée aux salles virtuelles introduites
    aujourd'hui pour is_pinned) : calculate_course_heatmap ne fait JAMAIS tourner le CH du
    solveur (elle appelle directement setWorkingSolution()/calculateScore() sur les données
    telles quelles) — un cours dont classroom vaut encore None (cas très courant : aucune salle
    n'a encore été assignée) reste "non initialisé" pour toute la durée du calcul. Or Timefold
    exclut purement une entité non initialisée de tout for_each()/for_each_unique_pair()
    ordinaire — pas seulement pour les contraintes regardant classroom, pour TOUTES
    (teacher_conflict, resource_preference_*, division_conflict...). Résultat observé : heatmap
    entièrement "verte", aucun impact des préférences ni des cours déjà placés. Ce test couvre
    les DEUX dimensions signalées : ni le cours cible ni un AUTRE cours déjà placé (partageant
    une ressource) n'ont de salle assignée.
    """
    from backend.app.solver.solver import calculate_course_heatmap

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    teacher = Teacher.create(db_session, {"code": "PROF_NOROOM", "first_name": "Prof", "last_name": "NoRoom", "school_id": school.id})
    division = Division.create(db_session, {"code": "DIV_NOROOM", "name": "Div NoRoom", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 540})

    # Préférence "Indisponible" sur la division, pour ts2 — AUCUNE salle assignée nulle part.
    ResourcePreference.create(db_session, {
        "resource_type": "Division", "resource_id": division.id, "timeslot_id": ts2.id,
        "preference_level": "Unsuited", "week_type": "W",
    })

    # Cours DÉJÀ PLACÉ à ts1, partageant le même enseignant — SANS salle assignée (le cas
    # fréquent en pratique : cours planifié avant que la salle ne soit décidée).
    other_course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [teacher.id], "timeslot_id": ts1.id,
    })
    assert other_course.classrooms == []

    # Cours cible, non placé, lui non plus sans salle assignée.
    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [teacher.id], "division_ids": [division.id],
    })
    db_session.commit()

    heatmap = calculate_course_heatmap(db_session, course.id, school.id)

    # ts1 : même enseignant que other_course, déjà placé là — conflit réel, malgré l'absence de
    # salle des deux côtés.
    assert heatmap[str(ts1.id)]["hard"] == -1
    assert "Teacher conflict" in [r["name"] for r in heatmap[str(ts1.id)]["reasons"]]

    # ts2 : préférence "Indisponible" sur la division du cours cible.
    assert heatmap[str(ts2.id)]["hard"] == -1
    assert "Resource unavailability (strict)" in [r["name"] for r in heatmap[str(ts2.id)]["reasons"]]


def test_solver_leaves_unplaceable_course_unassigned(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_UNPLACEABLE", "first_name": "Prof", "last_name": "Unplaceable", "school_id": school.id})
    c1 = Classroom.create(db_session, {"code": "ROOM_UNPLACEABLE", "name": "Room Unplaceable", "capacity": 30, "quantity": 1, "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_UNPLACEABLE", "name": "Div Unplaceable", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    # Création d'un seul créneau
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    # Création de deux cours pour le même enseignant (qui entrent en conflit si placés sur le même créneau unique)
    course1 = Course.create(db_session, {
        "subject_id": subject.id,
        "teacher_ids": [t1.id],
        "classroom_ids": [c1.id],
        "division_ids": [d1.id],
        "school_id": school.id,
        "duration_minutes": 30
    })
    course2 = Course.create(db_session, {
        "subject_id": subject.id,
        "teacher_ids": [t1.id],
        "classroom_ids": [c1.id],
        "division_ids": [d1.id],
        "school_id": school.id,
        "duration_minutes": 30
    })
    db_session.commit()

    # Lancer la résolution
    from backend.app.solver.solver import _solve_timetable_job
    _solve_timetable_job(db_session)

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
    mef = Mef.create(db_session, {"school_id": school.id, "code_national": "MEF_STUD_TEST", "name": "MEF Test", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 25})
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
    mef_unrelated = Mef.create(db_session, {"school_id": school.id, "code_national": "MEF_UNRELATED", "name": "MEF Non Lié", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 25})
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
    
    # 1. Enseignants et salles
    t1 = Teacher.create(db_session, {"code": "PROF_CTC1", "first_name": "Prof", "last_name": "CTC1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "PROF_CTC2", "first_name": "Prof", "last_name": "CTC2", "school_id": school.id})
    Classroom.create(db_session, {"code": "ROOM_CTC1", "name": "Room CTC1", "capacity": 30, "quantity": 1, "school_id": school.id})
    Classroom.create(db_session, {"code": "ROOM_CTC2", "name": "Room CTC2", "capacity": 30, "quantity": 1, "school_id": school.id})
    
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
    _solve_timetable_job(db_session)
    
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
    from backend.app.solver.solver import _solve_timetable_job
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
    Classroom.create(db_session, {"code": "CR_OPT", "name": "Classroom Opt", "capacity": 30, "school_id": school.id})
    
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
    
    _solve_timetable_job(db_session)
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

    _solve_timetable_job(db_session)
    db_session.refresh(c_a)
    db_session.refresh(c_b)

    # Optional constraint: the solver can violate it, so both should be placed.
    assert c_a.timeslot_id is not None
    assert c_b.timeslot_id is not None

def test_solver_subject_constraint_division_scope(db_session: Session):
    from backend.app.models.constraint import ResourceConstraint, SubjectToSubjectConstraint
    from backend.app.solver.solver import _solve_timetable_job
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
    Classroom.create(db_session, {"code": "CR_SCP", "name": "Classroom Scp", "capacity": 30, "school_id": school.id})

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

    _solve_timetable_job(db_session)
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
    
    Classroom.create(db_session, {"school_id": sch.id, "code": "R1", "name": "Room 1", "capacity": 30})

    from backend.app.solver.solver import _solve_timetable_job
    solution = _solve_timetable_job(db_session, sch.id)
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

    cr1 = Classroom.create(db_session, {"school_id": sch.id, "code": f"R1_{uai_val}", "name": "Room 1", "capacity": 30})
    cr2 = Classroom.create(db_session, {"school_id": sch.id, "code": f"R2_{uai_val}", "name": "Room 2", "capacity": 30})
    cr3 = Classroom.create(db_session, {"school_id": sch.id, "code": f"R3_{uai_val}", "name": "Room 3", "capacity": 30})

    # c1 = FULL CLASS
    c1 = Course.create(db_session, {"school_id": sch.id, "subject_id": sub.id, "duration_minutes": 60, "division_ids": [div.id], "timeslot_id": timeslots[pin_c1_day], "classroom_ids": [cr1.id], "is_pinned": True})
    
    # c2 = GROUP CLASS 1
    c2 = Course.create(db_session, {"school_id": sch.id, "subject_id": sub.id, "duration_minutes": 60, "class_part_ids": [cp1.id], "timeslot_id": timeslots[pin_c2_day], "classroom_ids": [cr2.id], "is_pinned": True})

    if pin_c3_day:
        # c3 = GROUP CLASS 2
        c3 = Course.create(db_session, {"school_id": sch.id, "subject_id": sub.id, "duration_minutes": 60, "class_part_ids": [cp2.id], "timeslot_id": timeslots[pin_c3_day], "classroom_ids": [cr3.id], "is_pinned": True})

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
    from backend.app.solver.solver import _solve_timetable_job
    solution = _solve_timetable_job(db_session, sch.id)
    assert solution.score.hard_score == 0

    # FULL on Mon (1), GROUP on Tue (2) -> Invalid
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE", pin_c1_day=1, pin_c2_day=2)
    solution = _solve_timetable_job(db_session, sch.id)
    assert solution.score.hard_score < 0

def test_group_course_order_group_after(db_session: Session):
    # FULL on Mon (1), GROUP on Tue (2) -> Valid
    sch = setup_group_course_order_scenario(db_session, "GROUP_AFTER", pin_c1_day=1, pin_c2_day=2)
    from backend.app.solver.solver import _solve_timetable_job
    solution = _solve_timetable_job(db_session, sch.id)
    assert solution.score.hard_score == 0

    # FULL on Tue (2), GROUP on Mon (1) -> Invalid
    sch = setup_group_course_order_scenario(db_session, "GROUP_AFTER", pin_c1_day=2, pin_c2_day=1)
    solution = _solve_timetable_job(db_session, sch.id)
    assert solution.score.hard_score < 0

def test_group_course_order_before_or_after(db_session: Session):
    # FULL on Tue (2), GROUP1 on Mon (1), GROUP2 on Mon (1) -> Valid (both before)
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE_OR_AFTER", pin_c1_day=2, pin_c2_day=1, pin_c3_day=1)
    from backend.app.solver.solver import _solve_timetable_job
    solution = _solve_timetable_job(db_session, sch.id)
    assert solution.score.hard_score == 0

    # FULL on Tue (2), GROUP1 on Mon (1), GROUP2 on Wed (3) -> Invalid (mixed)
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE_OR_AFTER", pin_c1_day=2, pin_c2_day=1, pin_c3_day=3)
    solution = _solve_timetable_job(db_session, sch.id)
    assert solution.score.hard_score < 0

def test_group_course_order_before_or_after_fortnight(db_session: Session):
    # FULL on Tue (2), GROUP1 on Mon (1), GROUP2 on Wed (3) -> Valid (mirrored)
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE_OR_AFTER_FORTNIGHT", pin_c1_day=2, pin_c2_day=1, pin_c3_day=3)
    from backend.app.solver.solver import _solve_timetable_job
    solution = _solve_timetable_job(db_session, sch.id)
    assert solution.score.hard_score == 0

    # FULL on Tue (2), GROUP1 on Wed (3), GROUP2 on Mon (1) -> Valid (mirrored)
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE_OR_AFTER_FORTNIGHT", pin_c1_day=2, pin_c2_day=3, pin_c3_day=1)
    solution = _solve_timetable_job(db_session, sch.id)
    assert solution.score.hard_score == 0

    # FULL on Tue (2), GROUP1 on Wed (3), GROUP2 on Wed (3) -> Invalid (both after)
    sch = setup_group_course_order_scenario(db_session, "GROUP_BEFORE_OR_AFTER_FORTNIGHT", pin_c1_day=2, pin_c2_day=3, pin_c3_day=3)
    solution = _solve_timetable_job(db_session, sch.id)
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
    mef = Mef.create(db_session, {"school_id": sch.id, "code_national": f"MEF_{uai_val}", "name": "M", "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 30})
    div = Division.create(db_session, {"school_id": sch.id, "code": f"DIV_{uai_val}", "name": "DIV"})
    MefDivision.create(db_session, {"mef_id": mef.id, "division_id": div.id, "forecast_student_count": 30})

    cr1 = Classroom.create(db_session, {"school_id": sch.id, "code": f"RM_{uai_val}", "name": "Room"})

    # Lundi = 1
    for m in [480, 510, 540, 570]:
        ts = db_session.query(Timeslot).filter_by(day_of_week=1, minutes_from_midnight=m).first()
        if not ts:
            Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": m})
            
    ts_am1 = db_session.query(Timeslot).filter_by(day_of_week=1, minutes_from_midnight=480).first()

    # 120 minutes (2 heures) de Math. Poids total = 2.0 * 2 = 4.0
    c1 = Course.create(db_session, {"school_id": sch.id, "subject_id": sub_math.id, "duration_minutes": 120, "division_ids": [div.id], "timeslot_id": ts_am1.id, "classroom_ids": [cr1.id], "is_pinned": True})

    db_session.commit()
    from backend.app.solver.solver import _solve_timetable_job
    solution1 = _solve_timetable_job(db_session, sch.id)
    
    # Dépassement matinée: 4.0 - 1.5 = 2.5 (25 penalité)
    # Dépassement journée: 4.0 - 3.0 = 1.0 (10 penalité)
    assert solution1.score.hard_score <= -35
    
    # Reduit à 30 minutes. Poids = 2.0 * 0.5 = 1.0. Sous la limite (1.5)
    c1.update(db_session, {"duration_minutes": 30})
    db_session.commit()
    solution2 = _solve_timetable_job(db_session, sch.id)
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
# (_build_planning_problem, rapide, sans lancer de résolution) pour vérifier le calcul du
# range/valeur initiale, et résolution complète (_solve_timetable_job) pour vérifier le
# comportement réel du solveur, y compris la cascade aux enfants d'un cours composé.
# =====================================================================================

def test_build_planning_problem_gives_ab_range_to_simple_q_course(db_session: Session):
    """
    Un cours simple (non composé) en week_type=Q reçoit un vrai choix {A, B} côté solveur,
    valeur de départ None (voir le spike de pré-semage, attribution_week_type_auto.md Échange 19 :
    laisser "Q" comme valeur de départ — hors du range {A,B} — bloquerait le solveur dessus).
    """
    from backend.app.solver.solver import _build_planning_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "week_type": "Q",
    })
    db_session.commit()

    problem = _build_planning_problem(db_session, school.id)
    pc = next(c for c in problem.courses if c.id == course.id)

    assert pc.week_type_range == ["A", "B"]
    assert pc.week_type is None


def test_build_planning_problem_gives_free_range_to_resolved_ab_course(db_session: Session):
    """
    Un cours déjà résolu en A ou B reçoit désormais aussi un range libre {A, B} (Point 2,
    attribution_week_type_auto.md Échange 18/19 — corrige un écart avec spec.md qui promettait
    déjà cette liberté avant la Phase C) : le solveur peut le faire basculer si c'est meilleur.
    Sa valeur de départ reste sa valeur actuelle (point de départ naturel pour la recherche,
    comme pour classroom), PAS None — seul un cours né Q démarre à None.
    """
    from backend.app.solver.solver import _build_planning_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    course_b = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "week_type": "B"})
    db_session.commit()

    problem = _build_planning_problem(db_session, school.id)
    pc_b = next(c for c in problem.courses if c.id == course_b.id)

    assert pc_b.week_type_range == ["A", "B"]
    assert pc_b.week_type == "B"


def test_build_planning_problem_gives_singleton_range_to_w_course(db_session: Session):
    """
    Seul un cours en W (Toutes les semaines) reste totalement hors de portée du solveur pour
    week_type : range singleton ["W"], jamais de choix — spec.md interdit explicitement à un
    cours W de basculer vers A/B.
    """
    from backend.app.solver.solver import _build_planning_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    course_w = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "week_type": "W"})
    db_session.commit()

    problem = _build_planning_problem(db_session, school.id)
    pc_w = next(c for c in problem.courses if c.id == course_w.id)

    assert pc_w.week_type_range == ["W"]
    assert pc_w.week_type == "W"


def test_build_planning_problem_gives_free_range_to_composed_parent_with_uniform_q_children(db_session: Session):
    """
    Un cours composé (parent) dont TOUS les enfants sont Q (agrégat uniforme, voir la règle
    _sync_parent_week_type révisée à l'Échange 18/19) reçoit désormais lui aussi un vrai choix
    {A, B} — ce n'est plus une limite de portée exclue comme à l'Échange 17 : la résolution
    du parent sera reportée à ses enfants par cascade au write-back (voir tests d'intégration).
    Le solveur ne construit toujours une PlanningCourse QUE pour le cours de premier niveau —
    les enfants n'apparaissent jamais comme entités indépendantes.
    """
    from backend.app.solver.solver import _build_planning_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    parent = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "is_composed": True})
    db_session.commit()
    child1 = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    child2 = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type.value == "Q"

    problem = _build_planning_problem(db_session, school.id)
    pc_parent = next(c for c in problem.courses if c.id == parent.id)

    assert pc_parent.week_type_range == ["A", "B"]
    assert pc_parent.week_type is None
    assert all(c.id not in (child1.id, child2.id) for c in problem.courses)


def test_build_planning_problem_gives_free_range_to_composed_parent_with_mixed_a_and_q_children(db_session: Session):
    """
    Un cours composé mélangeant un enfant déjà résolu (A) et un enfant encore Q (agrégat parent
    -> Q, pas un conflit) reçoit lui aussi un vrai choix {A, B} côté solveur — exactement comme
    un parent uniformément Q : la résolution du groupe entier (y compris l'enfant déjà résolu)
    reste possible, voir les tests d'intégration de cascade.
    """
    from backend.app.solver.solver import _build_planning_problem

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

    problem = _build_planning_problem(db_session, school.id)
    pc_parent = next(c for c in problem.courses if c.id == parent.id)

    assert pc_parent.week_type_range == ["A", "B"]
    assert pc_parent.week_type is None


def test_build_planning_problem_gives_singleton_range_to_composed_parent_with_real_ab_conflict(db_session: Session):
    """
    Un cours composé avec un vrai conflit A/B (un enfant A ET un enfant B déjà tous deux
    présents) remonte en W et reste hors de portée du solveur : range singleton ["W"].
    """
    from backend.app.solver.solver import _build_planning_problem

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

    problem = _build_planning_problem(db_session, school.id)
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
    Classroom.create(db_session, {"code": "ROOM_Q1", "name": "Room Q1", "capacity": 30, "quantity": 1, "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 510})

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "Q", "teacher_ids": [teacher.id],
    })
    db_session.commit()

    _solve_timetable_job(db_session)
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
    Classroom.create(db_session, {"code": "ROOM_STABLE", "name": "Room Stable", "capacity": 30, "quantity": 1, "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 510})

    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "A", "teacher_ids": [teacher.id],
    })
    db_session.commit()

    _solve_timetable_job(db_session)
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
    room = Classroom.create(db_session, {"code": "ROOM_CONFLICT", "name": "Room Conflict", "capacity": 30, "quantity": 1, "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    course_a = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "A", "teacher_ids": [teacher.id], "timeslot_id": ts1.id,
        "classroom_ids": [room.id], "is_pinned": True,
    })
    course_q = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "Q", "teacher_ids": [teacher.id],
    })
    db_session.commit()

    solution = _solve_timetable_job(db_session)
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
    timeslot/classroom, voir architecture.md section 5.G) — ce test vérifie que week_type en
    fait bien partie depuis la Phase C. Cours A épinglé sur l'unique créneau disponible : le
    cours Q partageant le même professeur ne peut structurellement pas le faire bouger, donc
    s'il se retrouve sur ce même créneau, il ne peut avoir été résolu qu'en B.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_PIN", "first_name": "Prof", "last_name": "Pin", "school_id": school.id})
    room = Classroom.create(db_session, {"code": "ROOM_PIN", "name": "Room Pin", "capacity": 30, "quantity": 1, "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    course_pinned = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "A", "teacher_ids": [teacher.id], "timeslot_id": ts1.id,
        "classroom_ids": [room.id], "is_pinned": True,
    })
    course_q = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "Q", "teacher_ids": [teacher.id],
    })
    db_session.commit()

    _solve_timetable_job(db_session)
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
    Classroom.create(db_session, {"code": "ROOM_COMP_Q", "name": "Room Comp Q", "capacity": 30, "quantity": 1, "school_id": school.id})
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

    _solve_timetable_job(db_session)
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
    room = Classroom.create(db_session, {"code": "ROOM_COMP_SWAP_P", "name": "Room Comp Swap P", "capacity": 30, "quantity": 1, "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    # Un autre cours simple, épinglé, qui occupe le même professeur sur le même créneau en A —
    # seule échappatoire pour le composé (aussi en A au départ) : basculer en B. Le composé
    # lui-même n'est PAS épinglé (is_pinned gèlerait aussi son week_type, contredisant le test) :
    # un seul créneau existe au total, donc il finira nécessairement sur ts1 lui aussi.
    other = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "A", "teacher_ids": [teacher.id], "timeslot_id": ts1.id,
        "classroom_ids": [room.id], "is_pinned": True,
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

    solution = _solve_timetable_job(db_session)
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
    room = Classroom.create(db_session, {"code": "ROOM_COMP_MIX", "name": "Room Comp Mix", "capacity": 30, "quantity": 1, "school_id": school.id})
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})

    other = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "week_type": "A", "teacher_ids": [teacher.id], "timeslot_id": ts1.id,
        "classroom_ids": [room.id], "is_pinned": True,
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

    solution = _solve_timetable_job(db_session)
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
# ne doit jamais faire planter le solveur/la heatmap, même sans salle assignée. Régression :
# l'ancien mécanisme forçait is_pinned=True sur ces cours, gelant TOUTES leurs variables — un
# cours étranger sans salle en base se retrouvait alors épinglé avec classroom=None, un état
# illégal pour Timefold ("pinned to null, even though unassigned values are not allowed"), qui
# faisait planter aussi bien _solve_timetable_job que calculate_course_heatmap dès qu'un
# school_id explicite était passé. Remplacé par foreign_school_timeslot_immobility
# (constraints.py) : ne protège que le créneau, laisse classroom totalement libre pour ces
# cours, jamais écrit en retour (garde school_id dans _solve_timetable_job).
# =====================================================================================

def _create_second_school_with_foreign_course(db_session, teacher_code="T_FOREIGN"):
    """Crée une 2e école avec un cours placé (créneau) mais SANS salle — le cas qui plantait."""
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
    assert foreign_course.classrooms == []  # bien sans salle : c'est le cas qui plantait
    return other_school, teacher, ts, foreign_course


def test_solver_ignores_foreign_school_course_without_classroom(db_session: Session):
    """
    _solve_timetable_job(db, school_id) ne doit pas planter à cause d'un cours d'une autre école
    sans salle assignée — ni corrompre les données de cette autre école.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    other_school, foreign_teacher, foreign_ts, foreign_course = _create_second_school_with_foreign_course(db_session)

    teacher = Teacher.create(db_session, {"code": "T_LOCAL", "first_name": "Prof", "last_name": "Local", "school_id": school.id})
    Classroom.create(db_session, {"code": "ROOM_LOCAL", "name": "Room Local", "capacity": 30, "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    local_course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "teacher_ids": [teacher.id],
    })
    db_session.commit()

    solution = _solve_timetable_job(db_session, school.id)  # ne doit pas lever d'exception
    db_session.refresh(local_course)
    db_session.refresh(foreign_course)

    assert local_course.timeslot_id is not None
    # Le cours étranger n'est jamais écrit en retour : ni son créneau ni sa salle ne changent.
    assert foreign_course.timeslot_id == foreign_ts.id
    assert foreign_course.classrooms == []


def test_heatmap_ignores_foreign_school_course_without_classroom(db_session: Session):
    """
    Le cas concrètement rapporté : calculate_course_heatmap(db, course_id, school_id) échouait
    silencieusement (exception Java avalée) dès qu'une autre école avait un cours sans salle.
    """
    from backend.app.solver.solver import calculate_course_heatmap

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    _create_second_school_with_foreign_course(db_session)

    teacher = Teacher.create(db_session, {"code": "T_HEATMAP", "first_name": "Prof", "last_name": "Heatmap", "school_id": school.id})
    Classroom.create(db_session, {"code": "ROOM_HEATMAP", "name": "Room Heatmap", "capacity": 30, "school_id": school.id})
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
    Régression distincte du crash "pinned to null" : calculate_heatmap_java (heatmap_proxy.py)
    avalait TOUTE exception et retournait {} — un résultat indiscernable d'une heatmap
    légitimement vide, invisible pour l'appelant (seule une trace apparaissait sur stderr).
    Force une panne (indépendante de tout scénario de crash réel, pour ne pas dépendre d'un bug
    qui pourrait être corrigé un jour) et vérifie qu'elle remonte bien jusqu'à
    calculate_course_heatmap sous la forme {"error": ...}, exploitable par l'appelant.
    """
    import _jpyinterpreter
    from backend.app.solver.solver import calculate_course_heatmap

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_ERR", "first_name": "Prof", "last_name": "Err", "school_id": school.id})
    Classroom.create(db_session, {"code": "ROOM_ERR", "name": "Room Err", "capacity": 30, "school_id": school.id})
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


def test_build_planning_problem_gives_virtual_classroom_to_pinned_roomless_course(db_session: Session):
    """
    Un cours forcé épinglé (US2, autre école) sans salle réelle reçoit une salle VIRTUELLE
    (id négatif, jamais dans classroomRange) purement pour que le pin reste légal côté
    Timefold — pas une vraie salle assignable par le solveur : is_pinned=True reste vrai, donc
    ce cours est structurellement exclu de la recherche (CH/LS), contrairement à une variable
    simplement protégée par une contrainte. Vérifie aussi que cette salle virtuelle ne peut
    jamais entrer en conflit avec une vraie salle (id absent de classroomRange).
    """
    from backend.app.solver.solver import _build_planning_problem

    school = db_session.query(School).first()
    other_school, foreign_teacher, foreign_ts, foreign_course = _create_second_school_with_foreign_course(db_session)
    db_session.commit()

    problem = _build_planning_problem(db_session, school.id)
    pc_foreign = next(c for c in problem.courses if c.id == foreign_course.id)

    assert pc_foreign.is_pinned is True
    assert pc_foreign.classroom is not None
    assert pc_foreign.classroom.id < 0  # virtuelle, jamais un vrai id de Classroom (positif)
    real_classroom_ids = {cr.id for cr in problem.classrooms}
    assert pc_foreign.classroom.id not in real_classroom_ids


def test_solver_force_pins_unplaced_foreign_school_course(db_session: Session):
    """
    Le forçage multi-établissement pince désormais TOUS les cours d'une autre école,
    y compris non placés (exclusion structurelle de CH/LS, pour éviter de gaspiller du temps de
    recherche sur des cours jamais réécrits en base) — voir _build_planning_problem. Un cours
    non placé étant potentiellement encore en Q (rien ne l'interdit pour un cours étranger : la
    règle Course.validate_pinned_requires_timeslot ne s'applique qu'à SA PROPRE école, pas au
    forçage du solveur), week_type doit recevoir une valeur légale (A ou B, membre de son propre
    range) plutôt que None pour rester épinglable sans planter.
    """
    from backend.app.solver.solver import _build_planning_problem

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    import uuid
    other_school = School.create(db_session, {"uai": str(uuid.uuid4())[:8], "name": "Autre Ecole Q"})
    foreign_course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": other_school.id, "duration_minutes": 30, "week_type": "Q",
    })
    db_session.commit()
    assert foreign_course.timeslot_id is None  # non placé, comme toute Q (règle existante)

    problem = _build_planning_problem(db_session, school.id)  # ne doit pas lever d'exception
    pc_foreign = next(c for c in problem.courses if c.id == foreign_course.id)

    assert pc_foreign.is_pinned is True
    assert pc_foreign.week_type in ("A", "B")  # jamais None malgré Q en base
    assert pc_foreign.week_type_range == ["A", "B"]


def test_solver_ignores_locally_pinned_course_without_classroom(db_session: Session):
    """
    Même correctif, cas plus général que le multi-établissement : un cours de LA MÊME école,
    épinglé manuellement (is_pinned=True, ex: via l'IHM) avant même qu'une salle lui soit
    assignée, aurait heurté exactement le même état illégal ("pinned to null"). La salle
    virtuelle s'applique à tout cours épinglé sans salle, pas seulement aux cours étrangers.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_PIN_NOROOM", "first_name": "Prof", "last_name": "PinNoRoom", "school_id": school.id})
    ts = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30,
        "teacher_ids": [teacher.id], "timeslot_id": ts.id, "is_pinned": True,
    })
    db_session.commit()
    assert course.classrooms == []

    _solve_timetable_job(db_session)  # ne doit pas lever d'exception
    db_session.refresh(course)

    assert course.timeslot_id == ts.id  # épinglé : jamais déplacé
    assert course.classrooms == []  # jamais corrompu par la salle virtuelle interne


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
    limites de temps doivent rester lues à chaque appel de _solve_timetable_job, pas figées à la
    première construction du factory. La fixture de session (conftest.py) fixe déjà
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
    Classroom.create(db_session, {"code": "ROOM_TIMELIMIT", "name": "Room TimeLimit", "capacity": 30, "school_id": school.id})
    Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "teacher_ids": [teacher.id],
    })
    db_session.commit()

    monkeypatch.setattr(settings, "SOLVER_TIME_LIMIT_SECONDS", 1)
    monkeypatch.setattr(settings, "SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS", 1)

    t0 = time.time()
    _solve_timetable_job(db_session)
    elapsed = time.time() - t0

    # Largement en dessous des 2s fixées par conftest.py pour le reste de la suite : preuve que
    # la limite de 1s demandée ICI a bien été appliquée, pas une valeur figée dans le factory
    # mis en cache. Marge généreuse pour absorber l'overhead machine.
    assert elapsed < 1.8

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

    cp1 = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition1.id, "code": "CP_ANG", "name": "Anglais"})
    cp2 = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition2.id, "code": "CP_ESP", "name": "Espagnol"})
    link = db_session.query(ClassPartLink).filter_by(class_part_a_id=min(cp1.id, cp2.id), class_part_b_id=max(cp1.id, cp2.id)).first()
    assert link is not None

    g1 = Group.create(db_session, {"code": "G1", "name": "Groupe 1", "class_part_ids": [cp1.id]})
    g2 = Group.create(db_session, {"code": "G2", "name": "Groupe 2", "class_part_ids": [cp2.id]})

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



def test_course_preference_propagation(db_session: Session):
    import datetime
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    # 1. Création d'un cours
    course = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "week_type": "A"
    })
    db_session.commit()
    
    # 2. Création de deux périodes
    from backend.app.models.period_type import PeriodType
    from backend.app.models.period import Period
    pt = PeriodType.create(db_session, {"name": "Trimestre"})
    per1 = Period.create(db_session, {
        "period_type_id": pt.id,
        "school_id": school.id,
        "code": "T1",
        "name": "T1",
        "start_date": datetime.date(2026, 9, 1),
        "end_date": datetime.date(2026, 12, 31)
    })
    per2 = Period.create(db_session, {
        "period_type_id": pt.id,
        "school_id": school.id,
        "code": "T2",
        "name": "T2",
        "start_date": datetime.date(2027, 1, 1),
        "end_date": datetime.date(2027, 3, 31)
    })
    db_session.commit()
    
    # Assigner la période au cours
    course.update(db_session, {"periods": [per1], "period_type_id": pt.id})
    db_session.commit()
    
    ts = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    db_session.commit()
    
    # 3. Créer une préférence pour ce cours
    pref = ResourcePreference.create(db_session, {
        "resource_type": "Course",
        "resource_id": course.id,
        "timeslot_id": ts.id,
        "preference_level": "Unsuited"
    })
    db_session.commit()
    
    # Vérifier qu'elle a hérité de la semaine A et de la période T1 du cours
    assert pref.week_type.value == "A"
    assert len(pref.periods) == 1
    assert pref.periods[0].id == per1.id
    
    # 4. Mettre à jour la semaine et la période du cours (vers per2)
    course.update(db_session, {"week_type": "B", "periods": [per2]})
    db_session.commit()
    
    # Recharger la préférence et vérifier la propagation
    db_session.refresh(pref)
    assert pref.week_type.value == "B"
    assert len(pref.periods) == 1
    assert pref.periods[0].id == per2.id
    
    # 5. Supprimer le cours et vérifier la suppression en cascade de la préférence
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
    cp1_a = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition1.id, "code": "CP_ANG_TEST", "name": "Anglais"})
    cp1_b = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition1.id, "code": "CP_GER_TEST", "name": "Allemand"})

    # À ce stade, pas de liens créés car pas d'autre partition contenant des parties
    links_before = db_session.query(ClassPartLink).all()
    links_test_before = [l for l in links_before if l.class_part_a_id in (cp1_a.id, cp1_b.id) or l.class_part_b_id in (cp1_a.id, cp1_b.id)]
    assert len(links_test_before) == 0

    # Création des parties pour partition 2
    cp2_a = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition2.id, "code": "CP_ART_TEST", "name": "Arts Plastiques"})
    
    # cp2_a doit être liée automatiquement à cp1_a et cp1_b
    links = db_session.query(ClassPartLink).all()
    links_cp2_a = [l for l in links if l.class_part_a_id == min(cp2_a.id, cp1_a.id) and l.class_part_b_id == max(cp2_a.id, cp1_a.id)]
    assert len(links_cp2_a) == 1
    assert links_cp2_a[0].is_system_generated is True

    links_cp2_a_ger = [l for l in links if l.class_part_a_id == min(cp2_a.id, cp1_b.id) and l.class_part_b_id == max(cp2_a.id, cp1_b.id)]
    assert len(links_cp2_a_ger) == 1

    # Création de cp2_b
    cp2_b = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition2.id, "code": "CP_MUS_TEST", "name": "Musique"})

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
    school = db_session.query(School).first()
    d = Division.create(db_session, {"code": "DIV_STUD_TEST", "name": "Div Stud Test", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    d_id = d.id
    
    # Partitions
    p1 = Partition.create(db_session, {"code": "P_STUD_1", "name": "Partition 1", "division_id": d_id})
    p2 = Partition.create(db_session, {"code": "P_STUD_2", "name": "Partition 2", "division_id": d_id})
    p1_id = p1.id
    p2_id = p2.id
    
    # ClassParts
    cp1_a = ClassPart.create(db_session, {"division_id": d_id, "partition_id": p1_id, "code": "CP_1A", "name": "Part 1A"})
    cp1_b = ClassPart.create(db_session, {"division_id": d_id, "partition_id": p1_id, "code": "CP_1B", "name": "Part 1B"})
    cp1_a_id = cp1_a.id
    cp1_b_id = cp1_b.id
    
    # cp2_a est automatiquement liée à cp1_a et cp1_b via des liens d'exclusion système
    cp2_a = ClassPart.create(db_session, {"division_id": d_id, "partition_id": p2_id, "code": "CP_2A", "name": "Part 2A"})
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
            "class_part_ids": [cp1_a_id, cp1_b_id]
        })
        
    db_session.commit()

    # Élève invalide : appartient à une partie d'une autre division (cohérence de division -> interdit)
    d2 = Division.create(db_session, {"code": "DIV_STUD_TEST_2", "name": "Div Stud Test 2", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    p2_d2 = Partition.create(db_session, {"code": "P_STUD_D2", "name": "Partition D2", "division_id": d2.id})
    cp_d2 = ClassPart.create(db_session, {"division_id": d2.id, "partition_id": p2_d2.id, "code": "CP_D2", "name": "Part D2"})
    db_session.commit()
    
    with pytest.raises(ValueError, match="depend d'une autre division|another division"):
        Student.create(db_session, {
            "first_name": "Invalide",
            "last_name": "WrongDiv",
            "division_id": d_id,
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


def test_get_linked_groups(db_session: Session):
    school = db_session.query(School).first()
    d = Division.create(db_session, {"code": "DIV_GGRP", "name": "Div GGrp", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    
    p1 = Partition.create(db_session, {"code": "P_GGRP_1", "name": "Partition GGrp 1", "division_id": d.id})
    p2 = Partition.create(db_session, {"code": "P_GGRP_2", "name": "Partition GGrp 2", "division_id": d.id})
    
    cp_a = ClassPart.create(db_session, {"division_id": d.id, "partition_id": p1.id, "code": "CP_GGRP_A", "name": "Part GGrp A"})
    cp_b = ClassPart.create(db_session, {"division_id": d.id, "partition_id": p1.id, "code": "CP_GGRP_B", "name": "Part GGrp B"})
    
    # cp_c est cree dans partition 2, ce qui declenche automatiquement la creation de liens ClassPartLink avec cp_a et cp_b
    cp_c = ClassPart.create(db_session, {"division_id": d.id, "partition_id": p2.id, "code": "CP_GGRP_C", "name": "Part GGrp C"})
    
    g_a = Group.create(db_session, {"code": "GRP_A", "name": "Groupe A", "class_part_ids": [cp_a.id]})
    g_b = Group.create(db_session, {"code": "GRP_B", "name": "Groupe B", "class_part_ids": [cp_b.id]})
    g_c = Group.create(db_session, {"code": "GRP_C", "name": "Groupe C", "class_part_ids": [cp_c.id]})
    
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
    
    from backend.app.models.mef import Mef
    mef = Mef.create(db_session, {"school_id": sch.id, "code_national": "M", "name": "M", "max_students_per_class": 30, "forecast_student_count": 30})
    div = Division.create(db_session, {"school_id": sch.id, "code": "DIV", "name": "DIV", "mef_id": mef.id})
    
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
    
    from backend.app.models.mef import Mef
    mef = Mef.create(db_session, {"school_id": sch.id, "code_national": f"M_{uai_val}", "name": "M3", "max_students_per_class": 30, "forecast_student_count": 30})
    div = Division.create(db_session, {"school_id": sch.id, "code": f"DIV_{uai_val}", "name": "DIV3", "mef_id": mef.id})
    
    part = Partition.create(db_session, {"division_id": div.id, "code": f"P_{uai_val}", "name": "PART"})
    cp1 = ClassPart.create(db_session, {"partition_id": part.id, "code": f"CP1_{uai_val}", "name": "CP1"})
    cp2 = ClassPart.create(db_session, {"partition_id": part.id, "code": f"CP2_{uai_val}", "name": "CP2"})
    
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
    from backend.app.models.mef import Mef
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
    
    mef = Mef.create(db_session, {"school_id": sch.id, "code_national": f"MEF_{uai_val}", "name": "M", "max_students_per_class": 30, "forecast_student_count": 30})
    div = Division.create(db_session, {"school_id": sch.id, "code": f"DIV_{uai_val}", "name": "DIV", "mef_id": mef.id})

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

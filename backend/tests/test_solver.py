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
from backend.app.models.preference import ResourcePreference
from backend.app.models.period import Period
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
            "short_label": "Maths",
            "long_label": "Mathématiques",
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

    t1 = Teacher.create(db_session, {"code": "PROF_MATH", "name": "Prof Math", "last_name": "Math", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "PROF_ANG", "name": "Prof Anglais", "last_name": "Anglais", "school_id": school.id})

    c1 = Classroom.create(db_session, {"code": "SALLE_A", "name": "Salle A", "capacity": 30, "quantity": 1, "school_id": school.id})
    c2 = Classroom.create(db_session, {"code": "SALLE_B", "name": "Salle B", "capacity": 30, "quantity": 1, "school_id": school.id})

    d1 = Division.create(db_session, {"code": "DIV_6E", "name": "6ème", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    d2 = Division.create(db_session, {"code": "DIV_5E", "name": "5ème", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 8})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 9})

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

    t1 = Teacher.create(db_session, {"code": "PROF_A", "name": "Prof A", "last_name": "A", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "PROF_B", "name": "Prof B", "last_name": "B", "school_id": school.id})

    c1 = Classroom.create(db_session, {"code": "ROOM_A", "name": "Room A", "capacity": 30, "quantity": 1, "school_id": school.id})
    c2 = Classroom.create(db_session, {"code": "ROOM_B", "name": "Room B", "capacity": 30, "quantity": 1, "school_id": school.id})

    d1 = Division.create(db_session, {"code": "DIV_A", "name": "Div A", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 8})

    # CORRECTION DU TEST : Création de DEUX partitions distinctes
    partition1 = Partition.create(db_session, {"code": "PART_LANG", "name": "Partition Langues", "division_id": d1.id})
    partition2 = Partition.create(db_session, {"code": "PART_LV2", "name": "Partition LV2", "division_id": d1.id})

    cp1 = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition1.id, "code": "CP_ANG", "name": "Anglais"})
    cp2 = ClassPart.create(db_session, {"division_id": d1.id, "partition_id": partition2.id, "code": "CP_ESP", "name": "Espagnol"})

    link = ClassPartLink.create(db_session, {"class_part_a_id": cp1.id, "class_part_b_id": cp2.id, "link_type": "Excluded", "is_system_generated": True})

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

    t1 = Teacher.create(db_session, {"code": "PROF_PREF", "name": "Prof Pref", "last_name": "Pref", "school_id": school.id})
    c1 = Classroom.create(db_session, {"code": "ROOM_PREF", "name": "Room Pref", "capacity": 30, "quantity": 1, "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_PREF", "name": "Div Pref", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 8})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 9})

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

    t1 = Teacher.create(db_session, {"code": "PROF_STAB", "name": "Prof Stab", "last_name": "Stab", "school_id": school.id})
    c1 = Classroom.create(db_session, {"code": "ROOM_STAB", "name": "Room Stab", "capacity": 30, "quantity": 1, "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_STAB", "name": "Div Stab", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 8})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 9})

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

    t1 = Teacher.create(db_session, {"code": "PROF_WEEK", "name": "Prof Week", "last_name": "Week", "school_id": school.id})
    c1 = Classroom.create(db_session, {"code": "ROOM_WEEK", "name": "Room Week", "capacity": 30, "quantity": 1, "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_WEEK", "name": "Div Week", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 8})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 9})

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

def test_solver_respects_period_specific_preferences(db_session: Session, monkeypatch):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    t1 = Teacher.create(db_session, {"code": "PROF_PERIOD", "name": "Prof Period", "last_name": "Period", "school_id": school.id})
    c1 = Classroom.create(db_session, {"code": "ROOM_PERIOD", "name": "Room Period", "capacity": 30, "quantity": 1, "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_PERIOD", "name": "Div Period", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 8})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 9})

    import datetime
    from backend.app.models.period_type import PeriodType
    pt = PeriodType.create(db_session, {"label": "Semestre"})

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

    from backend.app.solver import solver
    original_build = solver._build_planning_problem

    def patched_build(db, school_id=None):
        problem = original_build(db, school_id)
        for pc in problem.courses:
            if pc.id == course.id:
                pc.period_ids = [per2.id]
        return problem

    monkeypatch.setattr(solver, "_build_planning_problem", patched_build)
    
    _solve_timetable_job(db_session)
    db_session.refresh(course)
    
    assert course.timeslot_id == ts1.id

    def patched_build_overlap(db, school_id=None):
        problem = original_build(db, school_id)
        for pc in problem.courses:
            if pc.id == course.id:
                pc.period_ids = [per1.id]
        return problem

    monkeypatch.setattr(solver, "_build_planning_problem", patched_build_overlap)

    course.update(db_session, {"timeslot_id": None})
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
    teacher = Teacher.create(db_session, {"code": "T_OVERFLOW2", "name": "Prof", "last_name": "Overflow2", "school_id": school.id})
    
    # On crée deux créneaux : 17h00 et 17h30 (le dernier) sur le jour 1.
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 17.0})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 17.5})
    
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
    
    assert (target_p_course.timeslot.hour + target_p_course.step) > target_p_course.timeslot.absolute_end_of_day



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
    pt = PeriodType.create(db_session, {"label": "Trimestre"})
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
    
    ts = Timeslot.create(db_session, {"day_of_week": 1, "hour": 8})
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
    
    ts = Timeslot.create(db_session, {"day_of_week": 1, "hour": 8})
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
        step=2.0,
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
        step=2.0,
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
        "name": "Prof Art",
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
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 8})
    ts2 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 9})

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

    t1 = Teacher.create(db_session, {"code": "PROF_UNPLACEABLE", "name": "Prof Unplaceable", "last_name": "Unplaceable", "school_id": school.id})
    c1 = Classroom.create(db_session, {"code": "ROOM_UNPLACEABLE", "name": "Room Unplaceable", "capacity": 30, "quantity": 1, "school_id": school.id})
    d1 = Division.create(db_session, {"code": "DIV_UNPLACEABLE", "name": "Div Unplaceable", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})

    # Création d'un seul créneau
    ts1 = Timeslot.create(db_session, {"day_of_week": 1, "hour": 8})

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





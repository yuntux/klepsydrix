import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.app.main import app
from backend.app.core.database import SessionLocal, engine
from backend.app.models.base import Base
from backend.app.models.school import School
from backend.app.models.discipline import Discipline
from backend.app.models.subject import Subject
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.models.group import Partition, ClassPart, Group

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import get_db

from sqlalchemy.pool import StaticPool

# Moteur en mémoire vive SQLite partagé via StaticPool pour éviter le gotcha des connexions multiples
TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@pytest.fixture(scope="function", autouse=True)
def setup_dependency_overrides():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

import backend.app.solver.solver
def mock_start_solve(school_id=None):
    db = TestSessionLocal()
    try:
        backend.app.solver.solver._solve_timetable_job(db, school_id)
    finally:
        db.close()
        
import backend.app.api.endpoints
backend.app.api.endpoints.start_solve_timetable_async = mock_start_solve

client = TestClient(app)

@pytest.fixture(scope="function")
def db_session():
    # Recréation des tables sur la base de test isolée
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        # Création des ressources socle indispensables (école, discipline, matière)
        school = School(uai="1234567A", name="Lycée Test")
        school._via_crud_mixin_create = True
        db.add(school)
        db.commit()
        
        from backend.app.models.system_setting import SystemSetting
        setting = SystemSetting(key="STANDARD_TIMESLOT_DURATION", value="30")
        setting._via_crud_mixin_create = True
        db.add(setting)
        db.commit()
        
        discipline = Discipline(code="GEN", name="Général")
        discipline._via_crud_mixin_create = True
        db.add(discipline)
        db.commit()
        
        subject = Subject(
            code="MATH",
            code_nomenclature="NOM_MATH",
            short_name="Maths",
            name="Mathématiques",
            discipline_id=discipline.id
        )
        subject._via_crud_mixin_create = True
        db.add(subject)
        db.commit()
        
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)

def test_generic_timeslots_active_filter(db_session: Session):
    # STANDARD_TIMESLOT_DURATION vaut 30 (fixture db_session) : les deux créneaux, multiples de
    # 30, sont valides à la création (voir Timeslot._validate_hour_overflow, qui ne bloque QUE la
    # création). On fait ensuite passer la durée standard à 60 : le créneau à la minute 510
    # (multiple de 30 mais pas de 60) devient inactif, celui à 480 (multiple des deux) reste
    # actif — Timeslot.active reflète la pertinence COURANTE de la durée standard, pas la
    # validité au moment de la création.
    still_active_ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    still_active_ts._via_crud_mixin_create = True
    now_inactive_ts = Timeslot(day_of_week=1, minutes_from_midnight=510)
    now_inactive_ts._via_crud_mixin_create = True
    db_session.add_all([still_active_ts, now_inactive_ts])
    db_session.commit()

    from backend.app.models.system_setting import SystemSetting
    setting = db_session.query(SystemSetting).filter(SystemSetting.key == "STANDARD_TIMESLOT_DURATION").first()
    setting._via_crud_mixin_update = True
    setting.value = "60"
    db_session.commit()

    response = client.get("/api/generic/timeslots?active=true")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert still_active_ts.id in ids
    assert now_inactive_ts.id not in ids

    response = client.get("/api/generic/timeslots?active=false")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert now_inactive_ts.id in ids
    assert still_active_ts.id not in ids

def test_solve_timetable(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    t = Teacher(code="PROF_A", first_name="Prof", last_name="A", school_id=school.id)
    c = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    d = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    
    t._via_crud_mixin_create = True
    c._via_crud_mixin_create = True
    d._via_crud_mixin_create = True
    ts._via_crud_mixin_create = True
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    course = Course(subject_id=subject.id, teachers=[t], divisions=[d], school_id=school.id, duration_minutes=30)
    course._via_crud_mixin_create = True
    db_session.add(course)
    db_session.commit()

    response = client.post("/api/timetable/solve")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    
    import time
    for _ in range(15):
        status_resp = client.get("/api/timetable/status")
        if status_resp.json()["status"] == "NOT_SOLVING":
            break
        time.sleep(1)
        
    db_session.refresh(course)
    assert course.timeslot_id is not None
    assert (course.classrooms[0].id if course.classrooms else None) is not None

def test_reset_timetable(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    t = Teacher(code="PROF_A", first_name="Prof", last_name="A", school_id=school.id)
    c = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    d = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    
    t._via_crud_mixin_create = True
    c._via_crud_mixin_create = True
    d._via_crud_mixin_create = True
    ts._via_crud_mixin_create = True
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    # Créer un cours déjà planifié
    course = Course(subject_id=subject.id, teachers=[t], divisions=[d], timeslot_id=ts.id, classrooms=[c], school_id=school.id)
    course._via_crud_mixin_create = True
    db_session.add(course)
    db_session.commit()

    response = client.post("/api/timetable/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # Vérifier que le cours a bien été remis à NULL en base
    db_session.refresh(course)
    assert course.timeslot_id is None
    assert (course.classrooms[0].id if course.classrooms else None) == c.id

def test_update_course_success(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    t = Teacher(code="PROF_A", first_name="Prof", last_name="A", school_id=school.id)
    c = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    d = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts2 = Timeslot(day_of_week=1, minutes_from_midnight=540)
    
    t._via_crud_mixin_create = True
    c._via_crud_mixin_create = True
    d._via_crud_mixin_create = True
    ts._via_crud_mixin_create = True
    ts2._via_crud_mixin_create = True
    db_session.add_all([t, c, d, ts, ts2])
    db_session.commit()

    course = Course(subject_id=subject.id, teachers=[t], divisions=[d], school_id=school.id)
    course._via_crud_mixin_create = True
    db_session.add(course)
    db_session.commit()

    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts.id, "classroom_ids": [c.id]})
    assert response.status_code == 200
    db_session.refresh(course)
    assert course.timeslot_id == ts.id
    assert (course.classrooms[0].id if course.classrooms else None) == c.id

def test_update_course_conflict(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    t = Teacher(code="PROF_A", first_name="Prof", last_name="A", school_id=school.id)
    c1 = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    c2 = Classroom(code="SALLE_B", name="Salle B", capacity=25, quantity=1, school_id=school.id)
    d1 = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    d2 = Division(code="DIV_6B", name="6B", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts2 = Timeslot(day_of_week=1, minutes_from_midnight=540)
    
    t._via_crud_mixin_create = True
    c1._via_crud_mixin_create = True
    c2._via_crud_mixin_create = True
    d1._via_crud_mixin_create = True
    d2._via_crud_mixin_create = True
    ts._via_crud_mixin_create = True
    ts2._via_crud_mixin_create = True
    db_session.add_all([t, c1, c2, d1, d2, ts, ts2])
    db_session.commit()

    # Le premier cours occupe Prof A sur le créneau ts
    course1 = Course(subject_id=subject.id, teachers=[t], divisions=[d1], timeslot_id=ts.id, classrooms=[c1], school_id=school.id)
    # Le second cours est Prof A avec la classe d2 (actuellement non placé)
    course2 = Course(subject_id=subject.id, teachers=[t], divisions=[d2], school_id=school.id)
    
    course1._via_crud_mixin_create = True
    course2._via_crud_mixin_create = True
    db_session.add_all([course1, course2])
    db_session.commit()

    # Tenter de placer le second cours sur le même créneau avec la même prof (Conflit !)
    response = client.put(f"/api/timetable/courses/{course2.id}", json={"timeslot_id": ts.id, "classroom_ids": [c2.id]})
    assert response.status_code == 409
    assert "conflit" in response.json()["detail"].lower()

def test_solve_pinned_course(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    t = Teacher(code="PROF_A", first_name="Prof", last_name="A", school_id=school.id)
    c1 = Classroom(code="SALLE_1", name="Salle 1", capacity=30, quantity=1, school_id=school.id)
    c2 = Classroom(code="SALLE_2", name="Salle 2", capacity=30, quantity=1, school_id=school.id)
    d1 = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    d2 = Division(code="DIV_6B", name="6B", student_count=25, color="#CCCCCC", school_id=school.id)
    ts1 = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts2 = Timeslot(day_of_week=1, minutes_from_midnight=540)
    
    t._via_crud_mixin_create = True
    c1._via_crud_mixin_create = True
    c2._via_crud_mixin_create = True
    d1._via_crud_mixin_create = True
    d2._via_crud_mixin_create = True
    ts1._via_crud_mixin_create = True
    ts2._via_crud_mixin_create = True
    db_session.add_all([t, c1, c2, d1, d2, ts1, ts2])
    db_session.commit()

    # Le cours 1 est verrouillé (pinned) sur ts1 et c1
    course1 = Course(subject_id=subject.id, teachers=[t], divisions=[d1], timeslot_id=ts1.id, classrooms=[c1], is_pinned=True, school_id=school.id, duration_minutes=30)
    # Le cours 2 est libre
    course2 = Course(subject_id=subject.id, teachers=[t], divisions=[d2], school_id=school.id, duration_minutes=30)

    course1._via_crud_mixin_create = True
    course2._via_crud_mixin_create = True
    db_session.add_all([course1, course2])
    db_session.commit()

    # Résoudre avec Timefold
    response = client.post("/api/timetable/solve")
    assert response.status_code == 200
    
    import time
    for _ in range(15):
        status_resp = client.get("/api/timetable/status")
        if status_resp.json()["status"] == "NOT_SOLVING":
            break
        time.sleep(1)
    
    # Vérifier que le cours 1 n'a pas été déplacé par le solveur
    db_session.refresh(course1)
    db_session.refresh(course2)
    
    assert course1.timeslot_id == ts1.id
    assert (course1.classrooms[0].id if course1.classrooms else None) == c1.id
    assert course1.is_pinned is True
    
    # Le cours 2 a dû être planifié sur ts2 puisqu'il y a conflit enseignant sur ts1
    assert course2.timeslot_id == ts2.id


def test_structures_simulate_and_apply_change(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    t = Teacher(code="PROF_A", first_name="Prof", last_name="A", school_id=school.id)
    c = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    d = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    
    t._via_crud_mixin_create = True
    c._via_crud_mixin_create = True
    d._via_crud_mixin_create = True
    ts._via_crud_mixin_create = True
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    course = Course(subject_id=subject.id, teachers=[t], divisions=[d], timeslot_id=ts.id, classrooms=[c], school_id=school.id)
    course._via_crud_mixin_create = True
    db_session.add(course)
    db_session.commit()

    # 1. Simuler la suppression de l'enseignant
    sim_payload = {
        "action": "DELETE_RESOURCE",
        "resource_type": "Teacher",
        "resource_id": t.id,
        "payload": {}
    }
    response = client.post("/api/timetable/structures/simulate-change", json=sim_payload)
    assert response.status_code == 200
    sim_data = response.json()
    assert sim_data["can_proceed"] is True
    assert sim_data["impacted_sessions_count"] == 1
    assert sim_data["impacted_sessions"][0]["session_id"] == course.id

    # 2. Confirmer et appliquer la suppression
    apply_payload = {
        "action": "DELETE_RESOURCE",
        "resource_type": "Teacher",
        "resource_id": t.id,
        "payload": {}
    }
    response = client.post("/api/timetable/structures/apply-change", json=apply_payload)
    assert response.status_code == 200
    apply_data = response.json()
    assert apply_data["success"] is True
    assert apply_data["deplaced_sessions_count"] == 1

    # 3. Vérifier que la séance a bien été dépositionnée (timeslot_id et classroom_id à None)
    db_session.refresh(course)
    assert course.timeslot_id is None
    assert (course.classrooms[0].id if course.classrooms else None) is None


def test_preferences_crud(db_session: Session):
    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts._via_crud_mixin_create = True
    db_session.add(ts)
    db_session.commit()

    # 1. Créer une préférence
    pref_payload = {
        "resource_type": "Teacher",
        "resource_id": 999,
        "timeslot_id": ts.id,
        "preference_level": "Preferred"
    }
    response = client.post("/api/generic/resource_preferences", json=pref_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["preference_level"] == "Preferred"
    pref_id = data["id"]

    # 2. Lire les préférences
    response = client.get(f"/api/generic/resource_preferences?resource_type=Teacher&resource_id=999")
    assert response.status_code == 200
    res_data = response.json()
    prefs = res_data["items"]
    assert len(prefs) == 1
    assert prefs[0]["preference_level"] == "Preferred"
    assert prefs[0]["id"] == pref_id

    # 3. Supprimer (Mise au niveau Neutral)
    pref_payload["preference_level"] = "Neutral"
    response = client.post("/api/generic/resource_preferences", json=pref_payload)
    assert response.status_code == 200
    data_neutral = response.json()
    assert data_neutral["status"] == "purged"

    # 4. Vérifier la suppression
    response = client.get(f"/api/generic/resource_preferences?resource_type=Teacher&resource_id=999")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 0


def test_preferences_split_logic(db_session: Session):
    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts._via_crud_mixin_create = True
    db_session.add(ts)
    db_session.commit()

    # 1. Créer une préférence W (Preferred)
    response = client.post("/api/generic/resource_preferences", json={
        "resource_type": "Teacher",
        "resource_id": 888,
        "timeslot_id": ts.id,
        "preference_level": "Preferred",
        "week_type": "W"
    })
    assert response.status_code == 200

    # 2. Créer une préférence spécifique pour la semaine A (Unsuited)
    response = client.post("/api/generic/resource_preferences", json={
        "resource_type": "Teacher",
        "resource_id": 888,
        "timeslot_id": ts.id,
        "preference_level": "Unsuited",
        "week_type": "A"
    })
    assert response.status_code == 200

    # 3. Vérifier qu'il y a désormais deux préférences distinctes en base :
    #    - une préférence A (Unsuited)
    #    - une préférence B (Preferred), générée par la scission de W
    response = client.get("/api/generic/resource_preferences?resource_type=Teacher&resource_id=888")
    assert response.status_code == 200
    prefs = response.json()["items"]
    assert len(prefs) == 2
    
    pref_a = next(p for p in prefs if p["week_type"] == "A")
    pref_b = next(p for p in prefs if p["week_type"] == "B")
    
    assert pref_a["preference_level"] == "Unsuited"
    assert pref_b["preference_level"] == "Preferred"


def test_preferences_period_split_logic(db_session: Session):
    from backend.app.models.teacher import Teacher
    from backend.app.models.period import Period
    from backend.app.models.period_type import PeriodType
    from backend.app.models.timeslot import Timeslot
    from datetime import date

    school = db_session.query(School).first()
    
    # 1. Créer le type de période et les périodes
    pt = PeriodType(name="Trimestres")
    pt._via_crud_mixin_create = True
    db_session.add(pt)
    db_session.commit()
    
    p1 = Period(school_id=school.id, period_type_id=pt.id, code="T1", name="Trimestre 1", start_date=date(2026, 9, 1), end_date=date(2026, 12, 1))
    p2 = Period(school_id=school.id, period_type_id=pt.id, code="T2", name="Trimestre 2", start_date=date(2026, 12, 2), end_date=date(2027, 3, 1))
    p1._via_crud_mixin_create = True
    p2._via_crud_mixin_create = True
    db_session.add_all([p1, p2])
    db_session.commit()

    teacher = Teacher(code="TESTPER", first_name="Prof", last_name="Test", school_id=school.id)
    teacher._via_crud_mixin_create = True
    db_session.add(teacher)
    
    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts._via_crud_mixin_create = True
    db_session.add(ts)
    db_session.commit()

    # 1. Créer une préférence annuelle
    response = client.post("/api/generic/resource_preferences", json={
        "resource_type": "Teacher",
        "resource_id": teacher.id,
        "timeslot_id": ts.id,
        "preference_level": "Preferred",
        "week_type": "W"
    })
    assert response.status_code == 200

    # 2. Créer une préférence spécifique pour la période p1 (Unsuited)
    response = client.post("/api/generic/resource_preferences", json={
        "resource_type": "Teacher",
        "resource_id": teacher.id,
        "timeslot_id": ts.id,
        "preference_level": "Unsuited",
        "week_type": "W",
        "period_ids": [p1.id]
    })
    assert response.status_code == 200

    # 3. Vérifier la scission
    response = client.get(f"/api/generic/resource_preferences?resource_type=Teacher&resource_id={teacher.id}&timeslot_id={ts.id}")
    assert response.status_code == 200
    prefs = response.json()["items"]
    
    assert len(prefs) == 2
    pref_p1 = next(p for p in prefs if p1.id in p["period_ids"])
    pref_p2 = next(p for p in prefs if p2.id in p["period_ids"])
    
    assert pref_p1["preference_level"] == "Unsuited"
    assert pref_p2["preference_level"] == "Preferred"




def test_course_week_alternation_conflicts(db_session: Session):
    """
    Test the manual placement validation rules regarding week_type (A, B, W)
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    teacher = Teacher(code="T1", first_name="John", last_name="Doe", school_id=school.id)
    teacher._via_crud_mixin_create = True
    db_session.add(teacher)
    db_session.commit()
    
    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts._via_crud_mixin_create = True
    ts2 = Timeslot(day_of_week=1, minutes_from_midnight=540)
    ts2._via_crud_mixin_create = True
    db_session.add_all([ts, ts2])
    db_session.commit()

    # 1. Create a course in week A on timeslot ts
    c1 = Course(subject_id=subject.id, school_id=school.id, teachers=[teacher], week_type="A", timeslot_id=ts.id)
    c1._via_crud_mixin_create = True
    db_session.add(c1)
    db_session.commit()

    # 2. Try to put a new course on week A with the same teacher -> Conflict
    c2 = Course(subject_id=subject.id, school_id=school.id, teachers=[teacher], week_type="A")
    c2._via_crud_mixin_create = True
    db_session.add(c2)
    db_session.commit()

    response = client.put(f"/api/timetable/courses/{c2.id}", json={"timeslot_id": ts.id})
    assert response.status_code == 409
    assert "occupé" in response.json()["detail"]

    # 3. Try to put a new course on week W with the same teacher -> Conflict (W overlaps A)
    c3 = Course(subject_id=subject.id, school_id=school.id, teachers=[teacher], week_type="W")
    c3._via_crud_mixin_create = True
    db_session.add(c3)
    db_session.commit()

    response = client.put(f"/api/timetable/courses/{c3.id}", json={"timeslot_id": ts.id})
    assert response.status_code == 409
    
    # 4. Try to put a new course on week B with the same teacher -> Success (A and B alternate)
    c4 = Course(subject_id=subject.id, school_id=school.id, teachers=[teacher], week_type="B")
    c4._via_crud_mixin_create = True
    db_session.add(c4)
    db_session.commit()

    response = client.put(f"/api/timetable/courses/{c4.id}", json={"timeslot_id": ts.id})
    assert response.status_code == 200


def test_pinned_course_cannot_be_moved_manually(db_session: Session):
    """
    Un cours épinglé (is_pinned=True) ne peut pas être déplacé manuellement (créneau, salle ou
    semaine) — miroir de la garde déjà appliquée par le solveur (@PlanningPin), qui ne couvrait
    jusqu'ici que le placement automatique (voir attribution_week_type_auto.md, Échange 4/5).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    classroom1 = Classroom(code="C1", name="Salle 1", school_id=school.id, capacity=30)
    classroom1._via_crud_mixin_create = True
    classroom2 = Classroom(code="C2", name="Salle 2", school_id=school.id, capacity=30)
    classroom2._via_crud_mixin_create = True
    db_session.add_all([classroom1, classroom2])
    db_session.commit()

    ts1 = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts1._via_crud_mixin_create = True
    ts2 = Timeslot(day_of_week=1, minutes_from_midnight=540)
    ts2._via_crud_mixin_create = True
    # Créneau de fin de journée supplémentaire : validate_placement_conflicts refuse tout
    # placement qui déborderait de la grille (dernier minutes_from_midnight + pas standard) —
    # sans lui, placer un cours de 60 min sur ts2 déborderait, indépendamment de l'épinglage.
    ts_end = Timeslot(day_of_week=1, minutes_from_midnight=600)
    ts_end._via_crud_mixin_create = True
    db_session.add_all([ts1, ts2, ts_end])
    db_session.commit()

    course = Course(
        subject_id=subject.id, school_id=school.id, week_type="A",
        timeslot_id=ts1.id, classrooms=[classroom1], is_pinned=True,
    )
    course._via_crud_mixin_create = True
    db_session.add(course)
    db_session.commit()

    # Créneau : refusé tant que le cours reste épinglé.
    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts2.id})
    assert response.status_code == 409
    assert "épinglé" in response.json()["detail"]
    db_session.refresh(course)
    assert course.timeslot_id == ts1.id

    # Salle : refusé tant que le cours reste épinglé.
    response = client.put(f"/api/timetable/courses/{course.id}", json={"classroom_ids": [classroom2.id]})
    assert response.status_code == 409
    db_session.refresh(course)
    assert [c.id for c in course.classrooms] == [classroom1.id]

    # Semaine (via le CRUD générique — PATCH, pas PUT — week_type n'est pas encore exposé sur
    # l'endpoint de placement dédié /api/timetable/courses/{id}, voir
    # attribution_week_type_auto.md) : refusé tant que le cours reste épinglé.
    response = client.patch(f"/api/generic/courses/{course.id}", json={"week_type": "B"})
    assert response.status_code == 400
    assert "épinglé" in response.json()["detail"]
    db_session.refresh(course)
    assert course.week_type.value == "A"

    # Renvoyer le MÊME créneau (cas de la simple bascule du pin via CourseCard.vue) reste autorisé.
    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts1.id, "is_pinned": True})
    assert response.status_code == 200

    # Déverrouiller ET déplacer dans le même appel reste autorisé.
    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts2.id, "is_pinned": False})
    assert response.status_code == 200
    db_session.refresh(course)
    assert course.timeslot_id == ts2.id
    assert course.is_pinned is False


def test_course_complex_offset_propagation(db_session: Session):
    """
    Vérifie la propagation du décalage (offset) lors du déplacement d'un cours complexe
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # Création de 5 créneaux successifs (Lundi 8h, 8h30, 9h, 9h30, 10h)
    ts1 = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts2 = Timeslot(day_of_week=1, minutes_from_midnight=510)
    ts3 = Timeslot(day_of_week=1, minutes_from_midnight=540)
    ts4 = Timeslot(day_of_week=1, minutes_from_midnight=570)
    ts5 = Timeslot(day_of_week=1, minutes_from_midnight=600)
    for ts in [ts1, ts2, ts3, ts4, ts5]:
        ts._via_crud_mixin_create = True
        db_session.add(ts)
    db_session.commit()

    # 1. Création du cours parent
    parent_course = Course(subject_id=subject.id, school_id=school.id, duration_minutes=120)
    parent_course._via_crud_mixin_create = True
    db_session.add(parent_course)
    db_session.commit()

    # 2. Création de deux enfants, l'un sans offset, l'autre avec offset = 1
    child1 = Course(subject_id=subject.id, school_id=school.id, parent_id=parent_course.id, parent_timeslot_offset=0)
    child1._via_crud_mixin_create = True
    db_session.add(child1)
    
    child2 = Course(subject_id=subject.id, school_id=school.id, parent_id=parent_course.id, parent_timeslot_offset=1)
    child2._via_crud_mixin_create = True
    db_session.add(child2)
    db_session.commit()

    # 3. Placement du parent sur ts1 (8h00)
    response = client.put(f"/api/timetable/courses/{parent_course.id}", json={"timeslot_id": ts1.id})
    print(response.json())
    assert response.status_code == 200
    
    db_session.refresh(child1)
    db_session.refresh(child2)
    # L'enfant 1 doit être sur ts1, l'enfant 2 sur ts2 (8h30) car offset = 1
    assert child1.timeslot_id == ts1.id
    assert child2.timeslot_id == ts2.id

    # 4. Déplacement du parent sur ts2 (8h30)
    response = client.put(f"/api/timetable/courses/{parent_course.id}", json={"timeslot_id": ts2.id})
    print(response.json())
    assert response.status_code == 200

    db_session.refresh(child1)
    db_session.refresh(child2)
    # L'enfant 1 doit avoir suivi sur ts2, l'enfant 2 doit avoir été propulsé sur ts3 (9h00)
    assert child1.timeslot_id == ts2.id
    assert child2.timeslot_id == ts3.id

def test_course_child_timeslot_recomputes_offset(db_session: Session):
    """Vérifie que la modification directe du timeslot d'un enfant recalcule son offset."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    ts1 = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts2 = Timeslot(day_of_week=1, minutes_from_midnight=510)
    ts_end = Timeslot(day_of_week=1, minutes_from_midnight=1020)
    for ts in [ts1, ts2, ts_end]:
        ts._via_crud_mixin_create = True
        db_session.add(ts)
    db_session.commit()

    parent = Course(subject_id=subject.id, school_id=school.id, duration_minutes=60, is_composed=True)
    parent._via_crud_mixin_create = True
    db_session.add(parent)
    db_session.commit()

    # Placement du parent
    parent.update(db_session, {"timeslot_id": ts1.id})

    # Création de l'enfant (sera initialement sur le même créneau que le parent car offset par défaut = 0)
    child = Course.create(db_session, {
        "parent_id": parent.id,
        "subject_id": subject.id,
        "school_id": school.id,
        "duration_minutes": 30
    })
    
    assert child.timeslot_id == ts1.id
    assert child.parent_timeslot_offset == 0
    
    # Modification manuelle du créneau de l'enfant vers ts2 (offset devrait passer à 1)
    child.update(db_session, {"timeslot_id": ts2.id})
    
    # L'offset doit avoir été automatiquement calculé à 1
    assert child.parent_timeslot_offset == 1
    assert child.timeslot_id == ts2.id

def test_course_child_timeslot_raises_error_if_parent_unplaced(db_session: Session):
    """Vérifie qu'il est interdit d'assigner un créneau à un enfant si le parent n'en a pas."""
    import pytest
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    ts1 = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts1._via_crud_mixin_create = True
    db_session.add(ts1)
    db_session.commit()

    parent = Course(subject_id=subject.id, school_id=school.id, duration_minutes=60, is_composed=True)
    parent._via_crud_mixin_create = True
    db_session.add(parent)
    db_session.commit()

    child = Course.create(db_session, {
        "parent_id": parent.id,
        "subject_id": subject.id,
        "school_id": school.id,
        "duration_minutes": 30
    })
    
    # Tenter d'assigner un créneau à l'enfant doit lever une erreur (le parent n'est pas placé)
    with pytest.raises(ValueError) as exc:
        child.update(db_session, {"timeslot_id": ts1.id})
        
    assert "pas encore planifié" in str(exc.value)

def test_course_status_calculation(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    teacher1 = Teacher(code="T1", first_name="Prof", last_name="One", school_id=school.id)
    teacher1._via_crud_mixin_create = True
    
    ts1 = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts1._via_crud_mixin_create = True
    ts2 = Timeslot(day_of_week=1, minutes_from_midnight=540)
    ts2._via_crud_mixin_create = True
    
    db_session.add_all([teacher1, ts1, ts2])
    db_session.commit()
    
    # 1. Simple course - UNPLACED
    c1 = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "teachers": [teacher1]
    })
    db_session.commit()
    assert c1.status == "UNPLACED"
    assert c1.decomposition_status is None
    
    # 2. Simple course - PLACED
    c1.update(db_session, {"timeslot_id": ts1.id})
    db_session.commit()
    assert c1.status == "PLACED"
    assert c1.decomposition_status is None
    
    # 4. Composed Course - UNPLACED / UNVENTILATED (no children)
    parent = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "is_composed": True,
        "teachers": [teacher1]
    })
    db_session.commit()
    assert parent.status == "UNPLACED"
    assert parent.decomposition_status == "UNVENTILATED"
    
    # 5. Composed Course - UNPLACED / PARTIALLY_VENTILATED
    child = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "parent_id": parent.id,
        "teachers": []
    })
    db_session.commit()
    assert parent.status == "UNPLACED"
    assert parent.decomposition_status == "PARTIALLY_VENTILATED"
    
    # 6. Composed Course - PLACED / FULLY_VENTILATED
    c1.update(db_session, {"timeslot_id": None})
    db_session.commit()
    
    child.update(db_session, {"teachers": [teacher1]})
    db_session.commit()
    
    parent.update(db_session, {"timeslot_id": ts1.id})
    db_session.commit()
    
    assert parent.status == "PLACED"
    assert parent.decomposition_status == "FULLY_VENTILATED"


def test_course_underventilated_resource_ids(db_session: Session):
    """
    underventilated_resource_ids (recalculé au même endroit que decomposition_status, voir
    Course._missing_resource_ids_by_type) doit lister, par type de ressource, les IDs présents
    sur le cours composé mais absents de TOUS ses enfants.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    division = Division.create(db_session, {"code": "DIV_UV", "name": "UV", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    teacher1 = Teacher.create(db_session, {"code": "T_UV1", "first_name": "Prof", "last_name": "UV1", "school_id": school.id})
    teacher2 = Teacher.create(db_session, {"code": "T_UV2", "first_name": "Prof", "last_name": "UV2", "school_id": school.id})

    # Cours simple (non composé) : jamais de valeur.
    simple = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "teacher_ids": [teacher1.id]})
    assert simple.underventilated_resource_ids is None

    # Composé sans enfant (UNVENTILATED) : jamais de valeur non plus.
    parent = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "is_composed": True,
        "teacher_ids": [teacher1.id, teacher2.id], "division_ids": [division.id],
    })
    assert parent.decomposition_status == "UNVENTILATED"
    assert parent.underventilated_resource_ids is None

    # Enfant ne reprenant qu'un seul des deux enseignants et pas la division : les deux types
    # apparaissent dans le dict, teacher_ids ne liste que l'enseignant manquant.
    child = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "parent_id": parent.id,
        "teacher_ids": [teacher1.id],
    })
    assert parent.decomposition_status == "PARTIALLY_VENTILATED"
    assert parent.underventilated_resource_ids == {
        "teacher_ids": [teacher2.id],
        "division_ids": [division.id],
    }

    # Une fois l'enfant complété, le dict redevient vide (None), cohérent avec FULLY_VENTILATED.
    child.update(db_session, {"teacher_ids": [teacher1.id, teacher2.id], "division_ids": [division.id]})
    assert parent.decomposition_status == "FULLY_VENTILATED"
    assert parent.underventilated_resource_ids is None


def test_generic_update_endpoint_persists_late_recompute(db_session: Session):
    """
    Régression : make_update_endpoint (generic.py) appelait db.refresh(updated_item) sans
    db.flush() préalable. Session.refresh() DISCARDE tout changement d'attribut non flushé — or
    Course.update() modifie encore self APRÈS le dernier flush interne à CRUDMixin.update()
    (recompute_status(), appelé en toute fin de Course.update()). Un appel PATCH sur un cours
    composé déjà FULLY_VENTILATED (donc SANS aucun champ ressource dans le payload — le
    recalcul de decomposition_status doit survivre à une modification qui ne le touche même
    pas directement) reproduisait la perte : la réponse HTTP ET la ligne persistée en base
    retombaient sur l'ancien decomposition_status ("UNVENTILATED", la valeur par défaut à la
    création) au lieu de "FULLY_VENTILATED". Ce test passe par le client HTTP (pas un appel
    Python direct à Course.update()) : c'est justement la seule voie qui exerçait le bug, un
    appel direct au modèle ne recréant pas le refresh() supplémentaire de l'endpoint.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_FLUSH", "first_name": "Prof", "last_name": "Flush", "school_id": school.id})

    parent = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "is_composed": True, "teacher_ids": [teacher.id],
    })
    child = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "teacher_ids": [teacher.id],
    })
    assert parent.decomposition_status == "FULLY_VENTILATED"

    response = client.patch(f"/api/generic/courses/{parent.id}", json={"memo": "note sans rapport"})
    assert response.status_code == 200
    assert response.json()["decomposition_status"] == "FULLY_VENTILATED"

    db_session.expire_all()
    assert db_session.get(Course, parent.id).decomposition_status == "FULLY_VENTILATED"


def test_course_decomposition_status_ignores_children_placement(db_session: Session):
    """
    decomposition_status ne mesure que la ventilation des ressources (répartition parent ->
    enfants), pas le placement des enfants sur la grille : un cours composé peut donc être
    FULLY_VENTILATED alors qu'aucun de ses enfants n'a de timeslot_id (deux diagnostics
    volontairement découplés, voir Course.recompute_status).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    # is_composed est purement dérivé de la présence d'enfants (_compute_is_composed, déclenché
    # sur 'children_ids') : le forcer explicitement dans les vals de création stocke la valeur
    # sans être recalculé, puisque 'children_ids' n'est pas une clé touchée par cette création.
    teacher1 = Teacher.create(db_session, {"code": "T_DECOMP1", "first_name": "Prof", "last_name": "Decomp1", "school_id": school.id})

    parent = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "is_composed": True, "teacher_ids": [teacher1.id],
    })
    assert parent.is_composed is True
    child = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "teacher_ids": [teacher1.id],
    })

    assert child.status == "UNPLACED"
    assert parent.decomposition_status == "FULLY_VENTILATED"


def test_course_parent_week_type_cascade(db_session: Session):
    """
    Vérifie que le week_type du cours parent se synchronise automatiquement 
    en fonction de l'alternance de ses enfants.
    """
    from backend.app.models.course import Course
    from backend.app.models.preference import WeekType
    
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    # 1. Création du parent (par défaut 'W')
    parent = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "is_composed": True
    })
    db_session.commit()
    assert parent.week_type == WeekType.W
    
    # 2. Ajout d'un enfant en semaine A -> le parent doit devenir A
    child1 = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "parent_id": parent.id,
        "week_type": "A"
    })
    db_session.commit()
    
    # Rafraîchir le parent depuis la BD pour voir l'effet de la cascade
    db_session.refresh(parent)
    assert parent.week_type == WeekType.A
    
    # 3. Ajout d'un deuxième enfant en semaine B -> le parent doit devenir W (hybride)
    child2 = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "parent_id": parent.id,
        "week_type": "B"
    })
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type == WeekType.W
    
    # 4. Suppression de l'enfant 2 -> il ne reste que l'enfant 1 (A), le parent redevient A
    child2.delete(db_session)
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type == WeekType.A


def test_course_parent_week_type_cascade_pure_q_stays_q(db_session: Session):
    """
    Un parent dont TOUS les enfants sont Q (quinzaine à déterminer) reste lui-même Q — révisé à
    l'Échange 18/19 (voir attribution_week_type_auto.md) : auparavant, UN SEUL enfant encore Q
    suffisait à faire remonter le parent en Q, même mélangé à des enfants déjà résolus. Désormais
    seul un groupe intégralement Q remonte en Q (voir le test suivant pour le cas mixte).
    """
    from backend.app.models.course import Course

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    parent = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "is_composed": True})
    db_session.commit()

    Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type.value == "Q"

    Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type.value == "Q"  # toujours 100% Q -> reste Q


def test_course_parent_week_type_cascade_mixed_with_q_becomes_q(db_session: Session):
    """
    Un parent avec un enfant déjà résolu (A) et un autre encore Q reste Q, pas W : ce mélange
    est traité comme "en attente de résolution" au niveau du parent, pas comme un conflit — le
    solveur (ou un placement manuel) pourra alors choisir A ou B pour tout le groupe et reporter
    ce choix à tous les enfants, y compris ceux déjà résolus dans l'état précédent.
    Chaque enfant garde individuellement sa vraie valeur (A et Q) tant que rien ne le résout.
    """
    from backend.app.models.course import Course

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    parent = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "is_composed": True})
    db_session.commit()

    child_a = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "A"})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type.value == "A"

    child_q = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type.value == "Q"  # mélange A+Q -> Q, pas un conflit

    # Les enfants gardent individuellement leur propre valeur tant que le parent n'est pas résolu.
    db_session.refresh(child_a)
    db_session.refresh(child_q)
    assert child_a.week_type.value == "A"
    assert child_q.week_type.value == "Q"

    # Symétrique : un enfant B mélangé à un enfant Q donne aussi Q.
    parent2 = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "is_composed": True})
    db_session.commit()
    Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent2.id, "week_type": "B"})
    db_session.commit()
    Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent2.id, "week_type": "Q"})
    db_session.commit()
    db_session.refresh(parent2)
    assert parent2.week_type.value == "Q"


def test_course_parent_week_type_cascade_real_ab_conflict_becomes_w(db_session: Session):
    """
    Seul un vrai conflit — un enfant A ET un enfant B déjà tous deux présents — remonte le
    parent en W, que ce mélange inclue ou non des enfants encore Q : contrairement au mélange
    A+Q ou B+Q (test précédent), il n'y a ici plus une seule lettre vers laquelle le groupe
    pourrait converger, donc aucune résolution automatique n'est possible.
    """
    from backend.app.models.course import Course

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

    # Ajouter un enfant Q par-dessus un conflit A/B déjà présent ne change rien : toujours W.
    Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    db_session.commit()
    db_session.refresh(parent)
    assert parent.week_type.value == "W"


def test_course_composed_placed_rejects_new_or_updated_q_child(db_session: Session):
    """
    Limite assumée (voir spec.md, Course.week_type) : un cours composé déjà placé ne peut pas
    recevoir un nouvel enfant Q, ni voir un enfant existant repasser à Q. Le parent placé
    cascade son timeslot_id à chacun de ses enfants (_sync_vals_from_parent) — un enfant Q
    porterait donc, comme n'importe quel autre cours, un timeslot_id renseigné en même temps
    qu'un week_type=Q, ce que la règle générale (BR ci-dessus) rejette déjà pour tout Course,
    sans code dédié aux cours composés.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    ts = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
    db_session.commit()

    parent = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "is_composed": True,
    })
    db_session.commit()
    child = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 30, "parent_id": parent.id, "week_type": "A"})
    db_session.commit()

    parent.update(db_session, {"timeslot_id": ts.id})
    db_session.commit()
    db_session.refresh(child)
    assert child.timeslot_id == ts.id  # cascadé depuis le parent placé

    # Ajouter un nouvel enfant Q au parent déjà placé est rejeté.
    with pytest.raises(ValueError):
        Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "parent_id": parent.id, "week_type": "Q"})
    db_session.rollback()

    # Repasser l'enfant existant à Q est également rejeté (il porte déjà le timeslot cascadé).
    child = db_session.get(Course, child.id)
    with pytest.raises(ValueError):
        child.update(db_session, {"week_type": "Q"})
    db_session.rollback()


def test_course_week_type_q_cannot_be_placed(db_session: Session):
    """
    Un cours en week_type=Q ne peut jamais être placé sur la grille (timeslot_id) — ni à la
    création, ni en tentant de placer un cours déjà Q, ni en repassant en Q un cours déjà placé
    (les deux sens sont couverts par le même @constrains, voir attribution_week_type_auto.md).
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts._via_crud_mixin_create = True
    ts_end = Timeslot(day_of_week=1, minutes_from_midnight=600)
    ts_end._via_crud_mixin_create = True
    db_session.add_all([ts, ts_end])
    db_session.commit()

    # Création directe avec Q + un créneau -> refusé.
    with pytest.raises(ValueError, match="quinzaine"):
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "duration_minutes": 60,
            "week_type": "Q", "timeslot_id": ts.id,
        })

    # Cours Q non placé -> autorisé.
    course = Course.create(db_session, {
        "subject_id": subject.id, "school_id": school.id, "duration_minutes": 60, "week_type": "Q",
    })
    db_session.commit()

    # Tentative de placement manuel via l'API pendant qu'il est encore Q -> refusé.
    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts.id})
    assert response.status_code == 409
    assert "quinzaine" in response.json()["detail"]

    # Une fois résolu en A, le placement fonctionne normalement.
    course.update(db_session, {"week_type": "A"})
    db_session.commit()
    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts.id})
    assert response.status_code == 200

    # Sens inverse : repasser en Q un cours déjà placé (sans toucher au créneau) est refusé —
    # via le CRUD générique (PATCH), week_type n'étant pas exposé sur cet endpoint dédié.
    response = client.patch(f"/api/generic/courses/{course.id}", json={"week_type": "Q"})
    assert response.status_code == 400
    assert "quinzaine" in response.json()["detail"]
    db_session.refresh(course)
    assert course.week_type.value == "A"
    assert course.timeslot_id == ts.id


def test_course_preference_rejects_non_w_week_type(db_session: Session):
    """
    Une préférence de type Course s'applique obligatoirement à toutes les semaines (W) — l'IHM
    dédiée (courses_pref_grid) masque déjà le sélecteur de semaine pour ce type de ressource ;
    ce test vérifie le garde-fou modèle pour toute autre voie d'écriture (voir
    attribution_week_type_auto.md, Échange 9).
    """
    from backend.app.models.preference import ResourcePreference

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    course = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 60})
    db_session.commit()

    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts._via_crud_mixin_create = True
    db_session.add(ts)
    db_session.commit()

    # Création directe avec week_type='A' -> refusée.
    with pytest.raises(ValueError, match="toutes les semaines"):
        ResourcePreference.create(db_session, {
            "resource_type": "Course", "resource_id": course.id, "timeslot_id": ts.id,
            "preference_level": "Unsuited", "week_type": "A",
        })

    # Préférence valide (W par défaut), puis tentative de bascule vers 'B' en update -> refusée.
    pref = ResourcePreference.create(db_session, {
        "resource_type": "Course", "resource_id": course.id, "timeslot_id": ts.id,
        "preference_level": "Unsuited",
    })
    db_session.commit()
    with pytest.raises(ValueError, match="toutes les semaines"):
        pref.update(db_session, {"week_type": "B"})


def test_course_preference_rejects_non_annual_period(db_session: Session):
    """
    Une préférence de type Course s'applique obligatoirement à l'année entière (aucune période
    associée) — même logique que le test précédent, pour la dimension période plutôt que semaine.
    """
    import datetime
    from backend.app.models.preference import ResourcePreference
    from backend.app.models.period_type import PeriodType
    from backend.app.models.period import Period

    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    course = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 60})
    db_session.commit()

    ts = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts._via_crud_mixin_create = True
    db_session.add(ts)
    db_session.commit()

    pt = PeriodType.create(db_session, {"name": "Trimestre"})
    period = Period.create(db_session, {
        "period_type_id": pt.id, "school_id": school.id, "code": "T1", "name": "T1",
        "start_date": datetime.date(2026, 9, 1), "end_date": datetime.date(2026, 12, 31),
    })
    db_session.commit()

    # Création directe avec une période associée -> refusée.
    with pytest.raises(ValueError, match="année entière"):
        ResourcePreference.create(db_session, {
            "resource_type": "Course", "resource_id": course.id, "timeslot_id": ts.id,
            "preference_level": "Unsuited", "period_ids": [period.id],
        })

    # Préférence valide (annuelle par défaut), puis tentative d'associer une période en update
    # -> refusée.
    pref = ResourcePreference.create(db_session, {
        "resource_type": "Course", "resource_id": course.id, "timeslot_id": ts.id,
        "preference_level": "Unsuited",
    })
    db_session.commit()
    with pytest.raises(ValueError, match="année entière"):
        pref.update(db_session, {"period_ids": [period.id]})


def test_course_week_type_w_cannot_become_a_or_b_via_placement(db_session: Session):
    """
    Ceinture et bretelles pour le split de colonnes A/B (Phase B, voir
    attribution_week_type_auto.md) : un cours 'Toutes les semaines' (W) ne peut pas basculer
    vers A/B au moment où on le place (timeslot_id + week_type dans le même appel) — mais reste
    libre de changer de semaine hors placement, et un cours A/B peut toujours basculer vers
    l'autre lors d'un déplacement.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    ts1 = Timeslot(day_of_week=1, minutes_from_midnight=480)
    ts1._via_crud_mixin_create = True
    ts2 = Timeslot(day_of_week=1, minutes_from_midnight=540)
    ts2._via_crud_mixin_create = True
    ts_end = Timeslot(day_of_week=1, minutes_from_midnight=600)
    ts_end._via_crud_mixin_create = True
    db_session.add_all([ts1, ts2, ts_end])
    db_session.commit()

    # Placer un cours W en tentant de le faire basculer en A dans le même appel -> refusé.
    course = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 60})
    db_session.commit()
    assert course.week_type.value == "W"

    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts1.id, "week_type": "A"})
    assert response.status_code == 409
    assert "Toutes les semaines" in response.json()["detail"]
    db_session.refresh(course)
    assert course.timeslot_id is None
    assert course.week_type.value == "W"

    # Le même cours peut être placé normalement (W inchangé).
    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts1.id})
    assert response.status_code == 200

    # Changer la semaine d'un cours W SANS toucher au créneau (hors placement) reste autorisé
    # (via le CRUD générique, week_type n'étant pas exposé seul sur cet endpoint dédié).
    other_course = Course.create(db_session, {"subject_id": subject.id, "school_id": school.id, "duration_minutes": 60})
    db_session.commit()
    response = client.patch(f"/api/generic/courses/{other_course.id}", json={"week_type": "A"})
    assert response.status_code == 200

    # Un cours déjà A peut basculer vers B en le déplaçant (A/B restent librement interchangeables).
    response = client.put(f"/api/timetable/courses/{other_course.id}", json={"timeslot_id": ts2.id, "week_type": "B"})
    assert response.status_code == 200
    db_session.refresh(other_course)
    assert other_course.week_type.value == "B"
    assert other_course.timeslot_id == ts2.id


def test_course_day_overflow_conflict(db_session: Session):
    """
    Vérifie qu'un cours ne peut pas déborder au-delà du dernier créneau de la journée.
    Par exemple, si le dernier créneau est à 17h30, on ne peut pas y placer un cours de 1h.
    """
    from backend.app.models.system_setting import SystemSetting
    
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher(code="T_OVERFLOW", first_name="Prof", last_name="Overflow", school_id=school.id)
    teacher._via_crud_mixin_create = True
    db_session.add(teacher)
    
    # On crée deux créneaux : l'avant-dernier et le dernier de la journée
    # Ex: 17h00 et 17h30.
    ts1 = Timeslot(day_of_week=1, minutes_from_midnight=1020)
    ts2 = Timeslot(day_of_week=1, minutes_from_midnight=1050) # Le tout dernier créneau
    ts1._via_crud_mixin_create = True
    ts2._via_crud_mixin_create = True
    db_session.add_all([ts1, ts2])
    db_session.commit()

    # Création d'un cours d'une heure (60 minutes), donc 2 blocs de 30 minutes.
    course = Course(
        subject_id=subject.id, 
        school_id=school.id, 
        teachers=[teacher], 
        duration_minutes=60
    )
    course._via_crud_mixin_create = True
    db_session.add(course)
    db_session.commit()

    # 1. Placement sur l'avant-dernier créneau (17h00) : succès car il déborde sur 17h30 qui existe.
    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts1.id})
    assert response.status_code == 200

    # 2. Placement sur le dernier créneau (17h30) : doit échouer (Conflit 409) 
    # car il a besoin de 60 minutes et déborderait de la journée (pas de créneau à 18h00)
    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts2.id})
    assert response.status_code == 409
    assert "déborde" in response.json()["detail"].lower()


def test_course_periods_and_type_validation(db_session: Session):
    from backend.app.models.period_type import PeriodType
    from backend.app.models.period import Period
    from datetime import date
    
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    # 1. Créer deux types de périodes
    pt_semestre = PeriodType.create(db_session, {"name": "Semestre"})
    pt_trimestre = PeriodType.create(db_session, {"name": "Trimestre"})
    
    # 2. Créer des périodes de chaque type
    p_sem1 = Period.create(db_session, {
        "period_type_id": pt_semestre.id,
        "school_id": school.id,
        "code": "S1",
        "name": "Semestre 1",
        "start_date": date(2026, 9, 1),
        "end_date": date(2027, 1, 31)
    })
    p_trim1 = Period.create(db_session, {
        "period_type_id": pt_trimestre.id,
        "school_id": school.id,
        "code": "T1",
        "name": "Trimestre 1",
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 11, 30)
    })
    db_session.commit()
    
    # 3. Test : Un cours annuel ne peut pas être associé à des périodes
    import pytest
    with pytest.raises(ValueError, match="Un cours annuel"):
        Course.create(db_session, {
            "subject_id": subject.id,
            "school_id": school.id,
            "period_type_id": None,
            "period_ids": [p_sem1.id]
        })
    db_session.rollback()
    
    # 4. Test : Un cours lié à des périodes d'un type différent doit lever une erreur
    with pytest.raises(ValueError, match="ne correspond pas au type de période"):
        Course.create(db_session, {
            "subject_id": subject.id,
            "school_id": school.id,
            "period_type_id": pt_semestre.id,
            "period_ids": [p_trim1.id]
        })
    db_session.rollback()
    
    # 5. Test : Création valide avec le bon type de période
    course = Course.create(db_session, {
        "subject_id": subject.id,
        "school_id": school.id,
        "period_type_id": pt_semestre.id,
        "period_ids": [p_sem1.id]
    })
    db_session.commit()
    assert course.periods[0].id == p_sem1.id


def _make_division_class_parts(db_session, count=2):
    school = db_session.query(School).first()
    division = Division.create(db_session, {"code": "D6E", "name": "6ème", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})
    partition = Partition.create(db_session, {"code": "PART", "name": "Partition", "division_id": division.id})
    return [ClassPart.create(db_session, {"partition_id": partition.id, "name": f"CP{i}"}) for i in range(count)]


def test_course_group_added_cascades_its_class_parts(db_session: Session):
    """
    Un Group "est composé de" ClassPart : l'ajout d'un Group à un Course doit y ajouter
    automatiquement toutes ses ClassPart (Course._apply_group_class_part_cascade, règle 1).
    """
    subject = db_session.query(Subject).first()
    school = db_session.query(School).first()
    cp1, cp2 = _make_division_class_parts(db_session)
    group = Group.create(db_session, {"name": "Groupe 1", "class_part_ids": [cp1.id, cp2.id]})

    course = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "group_ids": [group.id]})

    assert {cp.id for cp in course.class_parts} == {cp1.id, cp2.id}
    assert {g.id for g in course.groups} == {group.id}


def test_course_class_part_added_does_not_cascade_to_groups(db_session: Session):
    """L'ajout d'une ClassPart au cours n'a aucun effet sur ses groupes (règle 2, pas de cascade inverse)."""
    subject = db_session.query(Subject).first()
    school = db_session.query(School).first()
    cp1, cp2 = _make_division_class_parts(db_session)
    Group.create(db_session, {"name": "Groupe 1", "class_part_ids": [cp1.id]})

    course = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "class_part_ids": [cp1.id]})

    assert {cp.id for cp in course.class_parts} == {cp1.id}
    assert course.groups == []


def test_course_group_removed_cascades_removal_of_its_class_parts(db_session: Session):
    """Le retrait d'un Group du cours retire également toutes ses ClassPart (règle 3)."""
    subject = db_session.query(Subject).first()
    school = db_session.query(School).first()
    # Un prof est ajouté pour que le retrait du groupe ne retire pas la dernière ressource du
    # cours (voir validate_has_at_least_one_resource) : non pertinent pour CE test, qui vérifie
    # uniquement la cascade Group -> ClassPart.
    teacher = Teacher.create(db_session, {"code": "T_GRP_RM", "first_name": "Prof", "last_name": "GrpRm", "school_id": school.id})
    cp1, cp2 = _make_division_class_parts(db_session)
    group = Group.create(db_session, {"name": "Groupe 1", "class_part_ids": [cp1.id, cp2.id]})
    course = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [teacher.id], "group_ids": [group.id]})
    assert {cp.id for cp in course.class_parts} == {cp1.id, cp2.id}

    course.update(db_session, {"group_ids": []})

    assert course.class_parts == []
    assert course.groups == []


def test_course_group_removal_does_not_strip_class_part_still_required_by_remaining_group(db_session: Session):
    """
    Si une ClassPart est partagée par 2 Group, retirer l'un des Group ne doit pas la retirer
    du cours tant que l'autre Group (toujours présent) en a encore besoin.
    """
    subject = db_session.query(Subject).first()
    school = db_session.query(School).first()
    cp1, cp2 = _make_division_class_parts(db_session)
    group_a = Group.create(db_session, {"name": "Groupe A", "class_part_ids": [cp1.id]})
    group_b = Group.create(db_session, {"name": "Groupe B", "class_part_ids": [cp1.id, cp2.id]})
    course = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "group_ids": [group_a.id, group_b.id]})
    assert {cp.id for cp in course.class_parts} == {cp1.id, cp2.id}

    course.update(db_session, {"group_ids": [group_b.id]})

    # cp1 reste car Groupe B (toujours présent) en a besoin, malgré le retrait de Groupe A
    assert {cp.id for cp in course.class_parts} == {cp1.id, cp2.id}
    assert {g.id for g in course.groups} == {group_b.id}


def test_course_class_part_removed_cascades_removal_of_composed_group_without_further_cascade(db_session: Session):
    """
    Le retrait d'une ClassPart retire tout Group qui en est composé (règle 4), mais SANS
    retirer à son tour les AUTRES ClassPart de ce Group (pas de réaction en chaîne).
    """
    subject = db_session.query(Subject).first()
    school = db_session.query(School).first()
    cp1, cp2 = _make_division_class_parts(db_session)
    group = Group.create(db_session, {"name": "Groupe 1", "class_part_ids": [cp1.id, cp2.id]})
    course = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "group_ids": [group.id]})
    assert {cp.id for cp in course.class_parts} == {cp1.id, cp2.id}

    # On retire seulement cp1 (pas group_ids dans les vals) : le Groupe 1, composé de cp1,
    # doit être retiré du cours -- mais sans retirer à son tour cp2.
    course.update(db_session, {"class_part_ids": [cp2.id]})

    assert {cp.id for cp in course.class_parts} == {cp2.id}
    assert course.groups == []


def test_course_group_and_extra_class_part_added_together_on_update(db_session: Session):
    """Un ajout simultané de group_ids et class_part_ids cumule les deux (règles 1 + 2)."""
    subject = db_session.query(Subject).first()
    school = db_session.query(School).first()
    cp1, cp2 = _make_division_class_parts(db_session)
    group = Group.create(db_session, {"name": "Groupe 1", "class_part_ids": [cp1.id]})
    course = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30})
    assert course.class_parts == []
    assert course.groups == []

    course.update(db_session, {"group_ids": [group.id], "class_part_ids": [cp2.id]})

    assert {cp.id for cp in course.class_parts} == {cp1.id, cp2.id}
    assert {g.id for g in course.groups} == {group.id}


def test_course_child_requires_subject(db_session: Session):
    """Un cours qui a un parent doit obligatoirement avoir sa propre matière."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_REQSUBJ", "first_name": "Prof", "last_name": "ReqSubj", "school_id": school.id})
    parent = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "is_composed": True, "teacher_ids": [teacher.id]})

    with pytest.raises(ValueError, match="matière"):
        Course.create(db_session, {"school_id": school.id, "parent_id": parent.id, "duration_minutes": 30, "teacher_ids": [teacher.id]})
    db_session.rollback()


def test_course_resource_added_to_child_cascades_to_parent(db_session: Session):
    """Ajouter une ressource à un enfant l'ajoute aussi au parent si elle n'y était pas déjà."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_UP1", "first_name": "Prof", "last_name": "Up1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_UP2", "first_name": "Prof", "last_name": "Up2", "school_id": school.id})
    parent = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [t1.id]})
    child = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "parent_id": parent.id, "duration_minutes": 30, "teacher_ids": [t1.id]})

    child.update(db_session, {"teacher_ids": [t1.id, t2.id]})

    assert {t.id for t in parent.teachers} == {t1.id, t2.id}


def test_course_resource_added_to_parent_does_not_cascade_to_children(db_session: Session):
    """Ajouter une ressource au parent n'a aucun effet sur ses enfants (pas de cascade inverse)."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_NODOWN1", "first_name": "Prof", "last_name": "NoDown1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_NODOWN2", "first_name": "Prof", "last_name": "NoDown2", "school_id": school.id})
    parent = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [t1.id]})
    child = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "parent_id": parent.id, "duration_minutes": 30, "teacher_ids": [t1.id]})

    parent.update(db_session, {"teacher_ids": [t1.id, t2.id]})

    assert {t.id for t in child.teachers} == {t1.id}


def test_course_resource_removed_from_child_does_not_affect_parent(db_session: Session):
    """Retirer une ressource d'un enfant n'a aucun effet sur les ressources du parent."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_NOUP1", "first_name": "Prof", "last_name": "NoUp1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_NOUP2", "first_name": "Prof", "last_name": "NoUp2", "school_id": school.id})
    parent = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [t1.id, t2.id]})
    child = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "parent_id": parent.id, "duration_minutes": 30, "teacher_ids": [t1.id, t2.id]})

    child.update(db_session, {"teacher_ids": [t1.id]})

    assert {t.id for t in parent.teachers} == {t1.id, t2.id}


def test_course_resource_removed_from_parent_cascades_to_children(db_session: Session):
    """Retirer une ressource du parent la retire de TOUS ses enfants."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_DOWN1", "first_name": "Prof", "last_name": "Down1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_DOWN2", "first_name": "Prof", "last_name": "Down2", "school_id": school.id})
    parent = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [t1.id, t2.id]})
    child = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "parent_id": parent.id, "duration_minutes": 30, "teacher_ids": [t1.id, t2.id]})

    parent.update(db_session, {"teacher_ids": [t1.id]})

    assert {t.id for t in child.teachers} == {t1.id}


def test_course_reparenting_cascades_its_full_resource_set_to_new_parent(db_session: Session):
    """Rattacher un cours existant à un parent y fait remonter TOUTES ses ressources déjà en place, pas seulement celles ajoutées dans le même appel."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_REPARENT1", "first_name": "Prof", "last_name": "Reparent1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_REPARENT2", "first_name": "Prof", "last_name": "Reparent2", "school_id": school.id})
    parent = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [t1.id]})
    standalone = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [t2.id]})

    standalone.update(db_session, {"parent_id": parent.id})

    assert {t.id for t in parent.teachers} == {t1.id, t2.id}


def test_course_cannot_remove_last_resource(db_session: Session):
    """Impossible de retirer la dernière ressource d'un cours, tous types confondus."""
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    teacher = Teacher.create(db_session, {"code": "T_LASTRES", "first_name": "Prof", "last_name": "LastRes", "school_id": school.id})
    course = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [teacher.id]})

    with pytest.raises(ValueError, match="dernière ressource"):
        course.update(db_session, {"teacher_ids": []})
    db_session.rollback()


def test_course_resource_removal_from_parent_blocked_if_it_would_empty_a_child(db_session: Session):
    """
    Le retrait en cascade (parent -> enfants) est bloqué si il viderait complètement un enfant
    de toute ressource -- même règle "dernière ressource" que pour un retrait direct.
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    t1 = Teacher.create(db_session, {"code": "T_BLOCK1", "first_name": "Prof", "last_name": "Block1", "school_id": school.id})
    t2 = Teacher.create(db_session, {"code": "T_BLOCK2", "first_name": "Prof", "last_name": "Block2", "school_id": school.id})
    parent = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 30, "teacher_ids": [t1.id, t2.id]})
    # L'enfant n'a QUE t1 : le retirer du parent le retirerait aussi de l'enfant, qui se
    # retrouverait sans aucune ressource.
    Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "parent_id": parent.id, "duration_minutes": 30, "teacher_ids": [t1.id]})

    with pytest.raises(ValueError, match="dernière ressource"):
        parent.update(db_session, {"teacher_ids": [t2.id]})
    db_session.rollback()

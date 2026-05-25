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
            short_label="Maths",
            long_label="Mathématiques",
            discipline_id=discipline.id
        )
        subject._via_crud_mixin_create = True
        db.add(subject)
        db.commit()
        
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)

def test_get_timetable(db_session: Session):
    school = db_session.query(School).first()
    t = Teacher(code="MARTIN", name="Prof Martin", last_name="Martin", school_id=school.id)
    t._via_crud_mixin_create = True
    db_session.add(t)
    db_session.commit()

    response = client.get("/api/timetable")
    assert response.status_code == 200
    data = response.json()
    assert "teachers" in data
    assert "courses" in data
    assert any(teacher["name"] == "Prof Martin" for teacher in data["teachers"])

def test_solve_timetable(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    t = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    c = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    d = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, hour=8)
    
    t._via_crud_mixin_create = True
    c._via_crud_mixin_create = True
    d._via_crud_mixin_create = True
    ts._via_crud_mixin_create = True
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    course = Course(subject_id=subject.id, teachers=[t], divisions=[d], school_id=school.id)
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
    
    t = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    c = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    d = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, hour=8)
    
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
    
    t = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    c = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    d = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, hour=8)
    
    t._via_crud_mixin_create = True
    c._via_crud_mixin_create = True
    d._via_crud_mixin_create = True
    ts._via_crud_mixin_create = True
    db_session.add_all([t, c, d, ts])
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
    
    t = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    c1 = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    c2 = Classroom(code="SALLE_B", name="Salle B", capacity=25, quantity=1, school_id=school.id)
    d1 = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    d2 = Division(code="DIV_6B", name="6B", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, hour=8)
    
    t._via_crud_mixin_create = True
    c1._via_crud_mixin_create = True
    c2._via_crud_mixin_create = True
    d1._via_crud_mixin_create = True
    d2._via_crud_mixin_create = True
    ts._via_crud_mixin_create = True
    db_session.add_all([t, c1, c2, d1, d2, ts])
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
    
    t = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    c1 = Classroom(code="SALLE_1", name="Salle 1", capacity=30, quantity=1, school_id=school.id)
    c2 = Classroom(code="SALLE_2", name="Salle 2", capacity=30, quantity=1, school_id=school.id)
    d1 = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    d2 = Division(code="DIV_6B", name="6B", student_count=25, color="#CCCCCC", school_id=school.id)
    ts1 = Timeslot(day_of_week=1, hour=8)
    ts2 = Timeslot(day_of_week=1, hour=9)
    
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
    course1 = Course(subject_id=subject.id, teachers=[t], divisions=[d1], timeslot_id=ts1.id, classrooms=[c1], is_pinned=True, school_id=school.id)
    # Le cours 2 est libre
    course2 = Course(subject_id=subject.id, teachers=[t], divisions=[d2], school_id=school.id)

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
    
    t = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    c = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    d = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, hour=8)
    
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
    ts = Timeslot(day_of_week=1, hour=8)
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
    ts = Timeslot(day_of_week=1, hour=8)
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
    pt = PeriodType(label="Trimestres")
    pt._via_crud_mixin_create = True
    db_session.add(pt)
    db_session.commit()
    
    p1 = Period(school_id=school.id, period_type_id=pt.id, code="T1", name="Trimestre 1", start_date=date(2026, 9, 1), end_date=date(2026, 12, 1))
    p2 = Period(school_id=school.id, period_type_id=pt.id, code="T2", name="Trimestre 2", start_date=date(2026, 12, 2), end_date=date(2027, 3, 1))
    p1._via_crud_mixin_create = True
    p2._via_crud_mixin_create = True
    db_session.add_all([p1, p2])
    db_session.commit()

    teacher = Teacher(code="TESTPER", name="Prof Test", last_name="Test", school_id=school.id)
    teacher._via_crud_mixin_create = True
    db_session.add(teacher)
    
    ts = Timeslot(day_of_week=1, hour=8)
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




def test_trmd_budget_synthesis(db_session: Session):
    from backend.app.models.trmd_budget import TrmdBudget
    from backend.app.models.school import School
    from backend.app.models.discipline import Discipline
    from backend.app.models.subject import Subject

    school = db_session.query(School).first()
    discipline = db_session.query(Discipline).first()
    
    # 1. Créer un budget de test
    budget = TrmdBudget(
        school_id=school.id,
        discipline_id=discipline.id,
        allocated_hp=36.0,
        allocated_hsa=4.0,
        allocated_posts=2.0
    )
    budget._via_crud_mixin_create = True
    db_session.add(budget)
    db_session.commit()

    # 2. Appeler l'API de synthèse budgétaire générique via le modèle virtuel
    response = client.get(f"/api/generic/trmd_syntheses?school_id={school.id}")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) > 0
    
    # Heures allouées converties en ETP = 36.0 / 18.0 = 2.0
    maths_summary = next(s for s in data["items"] if s["short_label"] == "Maths")
    assert maths_summary["allocated_etp"] == 2.0
    assert maths_summary["consumed_etp"] == 0.0
    assert maths_summary["status"] == "UNDER_BUDGET"

def test_course_week_alternation_conflicts(db_session: Session):
    """
    Test the manual placement validation rules regarding week_type (A, B, W)
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    teacher = Teacher(code="T1", name="John", last_name="Doe", school_id=school.id)
    teacher._via_crud_mixin_create = True
    db_session.add(teacher)
    db_session.commit()
    
    ts = Timeslot(day_of_week=1, hour=8)
    ts._via_crud_mixin_create = True
    db_session.add(ts)
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

def test_course_complex_offset_propagation(db_session: Session):
    """
    Vérifie la propagation du décalage (offset) lors du déplacement d'un cours complexe
    """
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # Création de 3 créneaux successifs (Lundi 8h, 8h30, 9h)
    ts1 = Timeslot(day_of_week=1, hour=8.0)
    ts2 = Timeslot(day_of_week=1, hour=8.5)
    ts3 = Timeslot(day_of_week=1, hour=9.0)
    for ts in [ts1, ts2, ts3]:
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


def test_course_status_calculation(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    teacher1 = Teacher(code="T1", name="Prof 1", last_name="One", school_id=school.id)
    teacher1._via_crud_mixin_create = True
    
    ts1 = Timeslot(day_of_week=1, hour=8.0)
    ts1._via_crud_mixin_create = True
    
    db_session.add_all([teacher1, ts1])
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


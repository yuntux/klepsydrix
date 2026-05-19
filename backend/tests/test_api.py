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
    try:
        db = TestSessionLocal()
        yield db
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
        school = School(uai="1234567A", name="Lycée Test", standard_timeslot_duration=30)
        db.add(school)
        db.commit()
        
        discipline = Discipline(code="GEN", name="Général")
        db.add(discipline)
        db.commit()
        
        subject = Subject(
            code="MATH",
            code_nomenclature="NOM_MATH",
            short_label="Maths",
            long_label="Mathématiques",
            discipline_id=discipline.id
        )
        db.add(subject)
        db.commit()
        
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)

def test_get_timetable(db_session: Session):
    school = db_session.query(School).first()
    t = Teacher(code="MARTIN", name="Prof Martin", last_name="Martin", school_id=school.id)
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
    
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    course = Course(subject_id=subject.id, teacher_id=t.id, division_id=d.id, school_id=school.id)
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
    assert course.classroom_id is not None

def test_reset_timetable(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    t = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    c = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    d = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, hour=8)
    
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    # Créer un cours déjà planifié
    course = Course(subject_id=subject.id, teacher_id=t.id, division_id=d.id, timeslot_id=ts.id, classroom_id=c.id, school_id=school.id)
    db_session.add(course)
    db_session.commit()

    response = client.post("/api/timetable/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # Vérifier que le cours a bien été remis à NULL en base
    db_session.refresh(course)
    assert course.timeslot_id is None
    assert course.classroom_id is None

def test_update_course_success(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    t = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    c = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    d = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, hour=8)
    
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    course = Course(subject_id=subject.id, teacher_id=t.id, division_id=d.id, school_id=school.id)
    db_session.add(course)
    db_session.commit()

    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts.id, "classroom_id": c.id})
    assert response.status_code == 200
    db_session.refresh(course)
    assert course.timeslot_id == ts.id
    assert course.classroom_id == c.id

def test_update_course_conflict(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()
    
    t = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    c1 = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    c2 = Classroom(code="SALLE_B", name="Salle B", capacity=25, quantity=1, school_id=school.id)
    d1 = Division(code="DIV_6A", name="6A", student_count=25, color="#CCCCCC", school_id=school.id)
    d2 = Division(code="DIV_6B", name="6B", student_count=25, color="#CCCCCC", school_id=school.id)
    ts = Timeslot(day_of_week=1, hour=8)
    
    db_session.add_all([t, c1, c2, d1, d2, ts])
    db_session.commit()

    # Le premier cours occupe Prof A sur le créneau ts
    course1 = Course(subject_id=subject.id, teacher_id=t.id, division_id=d1.id, timeslot_id=ts.id, classroom_id=c1.id, school_id=school.id)
    # Le second cours est Prof A avec la classe d2 (actuellement non placé)
    course2 = Course(subject_id=subject.id, teacher_id=t.id, division_id=d2.id, school_id=school.id)
    
    db_session.add_all([course1, course2])
    db_session.commit()

    # Tenter de placer le second cours sur le même créneau avec la même prof (Conflit !)
    response = client.put(f"/api/timetable/courses/{course2.id}", json={"timeslot_id": ts.id, "classroom_id": c2.id})
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
    
    db_session.add_all([t, c1, c2, d1, d2, ts1, ts2])
    db_session.commit()

    # Le cours 1 est verrouillé (pinned) sur ts1 et c1
    course1 = Course(subject_id=subject.id, teacher_id=t.id, division_id=d1.id, timeslot_id=ts1.id, classroom_id=c1.id, is_pinned=True, school_id=school.id)
    # Le cours 2 est libre
    course2 = Course(subject_id=subject.id, teacher_id=t.id, division_id=d2.id, school_id=school.id)

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
    assert course1.classroom_id == c1.id
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
    
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    course = Course(subject_id=subject.id, teacher_id=t.id, division_id=d.id, timeslot_id=ts.id, classroom_id=c.id, school_id=school.id)
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
    assert course.classroom_id is None


def test_preferences_crud(db_session: Session):
    ts = Timeslot(day_of_week=1, hour=8)
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

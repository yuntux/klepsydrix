import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.app.main import app
from backend.app.core.database import SessionLocal, engine
from backend.app.models.base import Base
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import get_db

TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///./test_sqlite.db"
test_engine = create_engine(
    TEST_SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    try:
        db = TestSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

import backend.app.solver.solver
def mock_start_solve():
    db = TestSessionLocal()
    try:
        backend.app.solver.solver._solve_timetable_job(db)
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
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)

def test_get_timetable(db_session: Session):
    # Insérer une donnée d'exemple
    t = Teacher(name="Prof Martin")
    db_session.add(t)
    db_session.commit()

    response = client.get("/api/timetable")
    assert response.status_code == 200
    data = response.json()
    assert "teachers" in data
    assert "courses" in data
    assert any(teacher["name"] == "Prof Martin" for teacher in data["teachers"])

def test_solve_timetable(db_session: Session):
    # Insérer jeu d'essai minimal
    t = Teacher(name="Prof A")
    c = Classroom(name="Salle A", capacity=30)
    d = Division(name="6A")
    ts = Timeslot(day_of_week=1, hour=8)
    
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    course = Course(subject="Maths", teacher_id=t.id, division_id=d.id)
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
    t = Teacher(name="Prof A")
    c = Classroom(name="Salle A", capacity=30)
    d = Division(name="6A")
    ts = Timeslot(day_of_week=1, hour=8)
    
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    # Créer un cours déjà planifié
    course = Course(subject="Maths", teacher_id=t.id, division_id=d.id, timeslot_id=ts.id, classroom_id=c.id)
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
    t = Teacher(name="Prof A")
    c = Classroom(name="Salle A", capacity=30)
    d = Division(name="6A")
    ts = Timeslot(day_of_week=1, hour=8)
    
    db_session.add_all([t, c, d, ts])
    db_session.commit()

    course = Course(subject="Maths", teacher_id=t.id, division_id=d.id)
    db_session.add(course)
    db_session.commit()

    response = client.put(f"/api/timetable/courses/{course.id}", json={"timeslot_id": ts.id, "classroom_id": c.id})
    assert response.status_code == 200
    db_session.refresh(course)
    assert course.timeslot_id == ts.id
    assert course.classroom_id == c.id


def test_update_course_conflict(db_session: Session):
    t = Teacher(name="Prof A")
    c1 = Classroom(name="Salle A", capacity=30)
    c2 = Classroom(name="Salle B", capacity=25)
    d1 = Division(name="6A")
    d2 = Division(name="6B")
    ts = Timeslot(day_of_week=1, hour=8)
    
    db_session.add_all([t, c1, c2, d1, d2, ts])
    db_session.commit()

    # Le premier cours occupe Prof A sur le créneau ts
    course1 = Course(subject="Maths", teacher_id=t.id, division_id=d1.id, timeslot_id=ts.id, classroom_id=c1.id)
    # Le second cours est Prof A avec la classe d2 (actuellement non placé)
    course2 = Course(subject="Maths", teacher_id=t.id, division_id=d2.id)
    
    db_session.add_all([course1, course2])
    db_session.commit()

    # Tenter de placer le second cours sur le même créneau avec la même prof (Conflit !)
    response = client.put(f"/api/timetable/courses/{course2.id}", json={"timeslot_id": ts.id, "classroom_id": c2.id})
    assert response.status_code == 409
    assert "conflit" in response.json()["detail"].lower()


def test_solve_pinned_course(db_session: Session):
    # Enseignants, Salles, Divisions et Créneaux
    t = Teacher(name="Prof A")
    c1 = Classroom(name="Salle 1", capacity=30)
    c2 = Classroom(name="Salle 2", capacity=30)
    d1 = Division(name="6A")
    d2 = Division(name="6B")
    ts1 = Timeslot(day_of_week=1, hour=8)
    ts2 = Timeslot(day_of_week=1, hour=9)
    
    db_session.add_all([t, c1, c2, d1, d2, ts1, ts2])
    db_session.commit()

    # Le cours 1 est verrouillé (pinned) sur ts1 et c1
    course1 = Course(subject="Maths", teacher_id=t.id, division_id=d1.id, timeslot_id=ts1.id, classroom_id=c1.id, is_pinned=True)
    # Le cours 2 est libre
    course2 = Course(subject="Histoire", teacher_id=t.id, division_id=d2.id)

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


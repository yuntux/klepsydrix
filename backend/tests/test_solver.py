import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.app.models.base import Base
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.solver.solver import _solve_timetable_job

# Moteur en mémoire vive dédié aux tests pour isolation totale et vitesse critique
TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="function")
def db_session():
    # Créer les tables sur une base de test en mémoire SQLite pour isolation totale
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)

def test_solver_resolves_timetable(db_session: Session):
    # 1. Alimentation minimale en base (2 enseignants, 2 salles, 2 divisions, 2 créneaux, 2 cours)
    t1 = Teacher(name="Prof Math")
    t2 = Teacher(name="Prof Anglais")
    db_session.add_all([t1, t2])
    db_session.commit()

    c1 = Classroom(name="Salle A", capacity=30)
    c2 = Classroom(name="Salle B", capacity=30)
    db_session.add_all([c1, c2])
    db_session.commit()

    d1 = Division(name="6ème")
    d2 = Division(name="5ème")
    db_session.add_all([d1, d2])
    db_session.commit()

    ts1 = Timeslot(day_of_week=1, hour=8)
    ts2 = Timeslot(day_of_week=1, hour=9)
    db_session.add_all([ts1, ts2])
    db_session.commit()

    # Création de deux cours qui partagent le même enseignant (Prof Math) et la même division (6ème).
    # Ils DOIVENT être planifiés sur des créneaux différents car un professeur ou une classe ne peut pas doubler
    course1 = Course(subject="Maths", teacher_id=t1.id, division_id=d1.id)
    course2 = Course(subject="Géométrie", teacher_id=t1.id, division_id=d1.id)
    db_session.add_all([course1, course2])
    db_session.commit()

    # 2. Exécution du solveur
    _solve_timetable_job(db_session)

    # 3. Rechargement des objets et assertions
    db_session.refresh(course1)
    db_session.refresh(course2)

    # Vérification que les deux cours ont reçu un créneau et une salle
    assert course1.timeslot_id is not None
    assert course2.timeslot_id is not None
    assert course1.classroom_id is not None
    assert course2.classroom_id is not None

    # Contrainte dure : les créneaux doivent être différents pour éviter le doublon d'enseignant et de division
    assert course1.timeslot_id != course2.timeslot_id

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

def test_solver_resolves_timetable(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # 1. Alimentation minimale en base (2 enseignants, 2 salles, 2 divisions, 2 créneaux, 2 cours)
    t1 = Teacher(code="PROF_MATH", name="Prof Math", last_name="Math", school_id=school.id)
    t2 = Teacher(code="PROF_ANG", name="Prof Anglais", last_name="Anglais", school_id=school.id)
    db_session.add_all([t1, t2])
    db_session.commit()

    c1 = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    c2 = Classroom(code="SALLE_B", name="Salle B", capacity=30, quantity=1, school_id=school.id)
    db_session.add_all([c1, c2])
    db_session.commit()

    d1 = Division(code="DIV_6E", name="6ème", student_count=25, color="#CCCCCC", school_id=school.id)
    d2 = Division(code="DIV_5E", name="5ème", student_count=25, color="#CCCCCC", school_id=school.id)
    db_session.add_all([d1, d2])
    db_session.commit()

    ts1 = Timeslot(day_of_week=1, hour=8)
    ts2 = Timeslot(day_of_week=1, hour=9)
    db_session.add_all([ts1, ts2])
    db_session.commit()

    # Création de deux cours qui partagent le même enseignant (Prof Math) et la même division (6ème).
    # Ils DOIVENT être planifiés sur des créneaux différents car un professeur ou une classe ne peut pas doubler
    course1 = Course(subject_id=subject.id, teacher_id=t1.id, division_id=d1.id, school_id=school.id)
    course2 = Course(subject_id=subject.id, teacher_id=t1.id, division_id=d1.id, school_id=school.id)
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

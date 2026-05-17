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


def test_solver_group_link_and_week_alternation(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # 1. Création des enseignants, classes et créneaux
    t1 = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    t2 = Teacher(code="PROF_B", name="Prof B", last_name="B", school_id=school.id)
    db_session.add_all([t1, t2])
    db_session.commit()

    c1 = Classroom(code="ROOM_A", name="Room A", capacity=30, quantity=1, school_id=school.id)
    c2 = Classroom(code="ROOM_B", name="Room B", capacity=30, quantity=1, school_id=school.id)
    db_session.add_all([c1, c2])
    db_session.commit()

    d1 = Division(code="DIV_A", name="Div A", student_count=25, color="#CCCCCC", school_id=school.id)
    db_session.add(d1)
    db_session.commit()

    ts1 = Timeslot(day_of_week=1, hour=8)
    db_session.add(ts1)
    db_session.commit()

    # 2. Création de partitions, parties de classe et d'un lien d'incompatibilité ClassPartLink
    partition = Partition(code="PART_1", name="Partition 1", division_id=d1.id)
    db_session.add(partition)
    db_session.commit()

    cp1 = ClassPart(division_id=d1.id, partition_id=partition.id, code="CP1", name="Partie 1")
    cp2 = ClassPart(division_id=d1.id, partition_id=partition.id, code="CP2", name="Partie 2")
    db_session.add_all([cp1, cp2])
    db_session.commit()

    # Le lien d'incompatibilité ordonné CP1 < CP2
    link = ClassPartLink(class_part_a_id=cp1.id, class_part_b_id=cp2.id, link_type="Excluded", is_system_generated=True)
    db_session.add(link)
    db_session.commit()

    # Création des groupes liés à ces parties
    g1 = Group(code="G1", name="Groupe 1")
    g1.class_parts.append(cp1)
    g2 = Group(code="G2", name="Groupe 2")
    g2.class_parts.append(cp2)
    db_session.add_all([g1, g2])
    db_session.commit()

    # 3. Premier cas : les deux cours sont hebdomadaires (week_type='T')
    # Comme il n'y a qu'un seul créneau disponible, ils ne peuvent pas coexister sans pénalité Hard.
    course1 = Course(subject_id=subject.id, teacher_id=t1.id, division_id=d1.id, group_id=g1.id, school_id=school.id)
    course2 = Course(subject_id=subject.id, teacher_id=t2.id, division_id=d1.id, group_id=g2.id, school_id=school.id)
    db_session.add_all([course1, course2])
    db_session.commit()

    # Modifier le type de semaine sur la session sous-jacente
    course1.sessions[0].week_type = "T"
    course2.sessions[0].week_type = "T"
    db_session.commit()

    # Exécution du solveur
    _solve_timetable_job(db_session)
    db_session.refresh(course1)
    db_session.refresh(course2)

    # 4. Deuxième cas : alternance Semaine A et Semaine B (week_type='A' et week_type='B')
    # Même avec un seul créneau temporel, ils PEUVENT coexister sur le même créneau car ils sont alternés.
    course1.sessions[0].week_type = "A"
    course2.sessions[0].week_type = "B"
    db_session.commit()

    _solve_timetable_job(db_session)
    db_session.refresh(course1)
    db_session.refresh(course2)

    # Ils ont été affectés au même créneau car ils sont en alternance A/B sans chevauchement !
    assert course1.timeslot_id is not None
    assert course2.timeslot_id is not None
    assert course1.timeslot_id == course2.timeslot_id

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
        school = School(uai="1234567A", name="Lycée Test")
        school._via_crud_mixin_create = True
        db.add(school)
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

def test_solver_resolves_timetable(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # 1. Alimentation minimale en base (2 enseignants, 2 salles, 2 divisions, 2 créneaux, 2 cours)
    t1 = Teacher(code="PROF_MATH", name="Prof Math", last_name="Math", school_id=school.id)
    t2 = Teacher(code="PROF_ANG", name="Prof Anglais", last_name="Anglais", school_id=school.id)
    t1._via_crud_mixin_create = True
    t2._via_crud_mixin_create = True
    db_session.add_all([t1, t2])
    db_session.commit()

    c1 = Classroom(code="SALLE_A", name="Salle A", capacity=30, quantity=1, school_id=school.id)
    c2 = Classroom(code="SALLE_B", name="Salle B", capacity=30, quantity=1, school_id=school.id)
    c1._via_crud_mixin_create = True
    c2._via_crud_mixin_create = True
    db_session.add_all([c1, c2])
    db_session.commit()

    d1 = Division(code="DIV_6E", name="6ème", student_count=25, color="#CCCCCC", school_id=school.id)
    d2 = Division(code="DIV_5E", name="5ème", student_count=25, color="#CCCCCC", school_id=school.id)
    d1._via_crud_mixin_create = True
    d2._via_crud_mixin_create = True
    db_session.add_all([d1, d2])
    db_session.commit()

    ts1 = Timeslot(day_of_week=1, hour=8)
    ts2 = Timeslot(day_of_week=1, hour=9)
    ts1._via_crud_mixin_create = True
    ts2._via_crud_mixin_create = True
    db_session.add_all([ts1, ts2])
    db_session.commit()

    # Création de deux cours qui partagent le même enseignant (Prof Math) et la même division (6ème).
    # Ils DOIVENT être planifiés sur des créneaux différents car un professeur ou une classe ne peut pas doubler
    course1 = Course(subject_id=subject.id, teachers=[t1], divisions=[d1], school_id=school.id)
    course2 = Course(subject_id=subject.id, teachers=[t1], divisions=[d1], school_id=school.id)
    course1._via_crud_mixin_create = True
    course2._via_crud_mixin_create = True
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
    assert course1.classrooms[0].id if course1.classrooms else None is not None
    assert course2.classrooms[0].id if course2.classrooms else None is not None

    # Contrainte dure : les créneaux doivent être différents pour éviter le doublon d'enseignant et de division
    assert course1.timeslot_id != course2.timeslot_id


def test_solver_group_link_and_week_alternation(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # 1. Création des enseignants, classes et créneaux
    t1 = Teacher(code="PROF_A", name="Prof A", last_name="A", school_id=school.id)
    t2 = Teacher(code="PROF_B", name="Prof B", last_name="B", school_id=school.id)
    t1._via_crud_mixin_create = True
    t2._via_crud_mixin_create = True
    db_session.add_all([t1, t2])
    db_session.commit()

    c1 = Classroom(code="ROOM_A", name="Room A", capacity=30, quantity=1, school_id=school.id)
    c2 = Classroom(code="ROOM_B", name="Room B", capacity=30, quantity=1, school_id=school.id)
    c1._via_crud_mixin_create = True
    c2._via_crud_mixin_create = True
    db_session.add_all([c1, c2])
    db_session.commit()

    d1 = Division(code="DIV_A", name="Div A", student_count=25, color="#CCCCCC", school_id=school.id)
    d1._via_crud_mixin_create = True
    db_session.add(d1)
    db_session.commit()

    ts1 = Timeslot(day_of_week=1, hour=8)
    ts1._via_crud_mixin_create = True
    db_session.add(ts1)
    db_session.commit()

    # 2. Création de partitions, parties de classe et d'un lien d'incompatibilité ClassPartLink
    partition = Partition(code="PART_1", name="Partition 1", division_id=d1.id)
    partition._via_crud_mixin_create = True
    db_session.add(partition)
    db_session.commit()

    cp1 = ClassPart(division_id=d1.id, partition_id=partition.id, code="CP1", name="Partie 1")
    cp2 = ClassPart(division_id=d1.id, partition_id=partition.id, code="CP2", name="Partie 2")
    cp1._via_crud_mixin_create = True
    cp2._via_crud_mixin_create = True
    db_session.add_all([cp1, cp2])
    db_session.commit()

    # Le lien d'incompatibilité ordonné CP1 < CP2
    link = ClassPartLink(class_part_a_id=cp1.id, class_part_b_id=cp2.id, link_type="Excluded", is_system_generated=True)
    link._via_crud_mixin_create = True
    db_session.add(link)
    db_session.commit()

    # Création des groupes liés à ces parties
    g1 = Group(code="G1", name="Groupe 1")
    g1.class_parts.append(cp1)
    g2 = Group(code="G2", name="Groupe 2")
    g2.class_parts.append(cp2)
    g1._via_crud_mixin_create = True
    g2._via_crud_mixin_create = True
    db_session.add_all([g1, g2])
    db_session.commit()

    # 3. Premier cas : les deux cours sont hebdomadaires (week_type='W')
    # Comme il n'y a qu'un seul créneau disponible, ils ne peuvent pas coexister sans pénalité Hard.
    course1 = Course(subject_id=subject.id, teachers=[t1], divisions=[d1], groups=[g1], school_id=school.id)
    course2 = Course(subject_id=subject.id, teachers=[t2], divisions=[d1], groups=[g2], school_id=school.id)
    course1._via_crud_mixin_create = True
    course2._via_crud_mixin_create = True
    db_session.add_all([course1, course2])
    db_session.commit()

    # Modifier le type de semaine sur la session sous-jacente
    course1.update(db_session, {"week_type": "W"})
    course2.update(db_session, {"week_type": "W"})
    db_session.commit()

    # Exécution du solveur
    _solve_timetable_job(db_session)
    db_session.refresh(course1)
    db_session.refresh(course2)

    # 4. Deuxième cas : alternance Semaine A et Semaine B (week_type='A' et week_type='B')
    # Même avec un seul créneau temporel, ils PEUVENT coexister sur le même créneau car ils sont alternés.
    course1.update(db_session, {"timeslot_id": None})
    course2.update(db_session, {"timeslot_id": None})
    course1.update(db_session, {"week_type": "A"})
    course2.update(db_session, {"week_type": "B"})
    db_session.commit()

    _solve_timetable_job(db_session)
    db_session.refresh(course1)
    db_session.refresh(course2)

    # Ils ont été affectés au même créneau car ils sont en alternance A/B sans chevauchement !
    assert course1.timeslot_id is not None
    assert course2.timeslot_id is not None
    assert course1.timeslot_id == course2.timeslot_id


def test_solver_respects_preferences(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # 1. Création Enseignant, Salle, Division, Créneaux
    t1 = Teacher(code="PROF_PREF", name="Prof Pref", last_name="Pref", school_id=school.id)
    t1._via_crud_mixin_create = True
    db_session.add(t1)
    db_session.commit()

    c1 = Classroom(code="ROOM_PREF", name="Room Pref", capacity=30, quantity=1, school_id=school.id)
    c1._via_crud_mixin_create = True
    db_session.add(c1)
    db_session.commit()

    d1 = Division(code="DIV_PREF", name="Div Pref", student_count=25, color="#CCCCCC", school_id=school.id)
    d1._via_crud_mixin_create = True
    db_session.add(d1)
    db_session.commit()

    ts1 = Timeslot(day_of_week=1, hour=8) # Indisponible (Unsuited)
    ts2 = Timeslot(day_of_week=1, hour=9) # Préféré (Preferred)
    ts1._via_crud_mixin_create = True
    ts2._via_crud_mixin_create = True
    db_session.add_all([ts1, ts2])
    db_session.commit()

    # 2. Création du vœu "Unsuited" sur ts1 et "Preferred" sur ts2
    p1 = ResourcePreference(resource_type="Teacher", resource_id=t1.id, timeslot_id=ts1.id, preference_level="Unsuited")
    p2 = ResourcePreference(resource_type="Teacher", resource_id=t1.id, timeslot_id=ts2.id, preference_level="Preferred")
    p1._via_crud_mixin_create = True
    p2._via_crud_mixin_create = True
    db_session.add_all([p1, p2])
    db_session.commit()

    # 3. Création du cours à planifier
    course = Course(subject_id=subject.id, teachers=[t1], divisions=[d1], school_id=school.id)
    course._via_crud_mixin_create = True
    db_session.add(course)
    db_session.commit()

    # 4. Résoudre
    _solve_timetable_job(db_session)
    db_session.refresh(course)

    # 5. Assertion : Le cours DOIT être planifié sur ts2 (Preferred) car ts1 est Unsuited (Strictement interdit)
    assert course.timeslot_id is not None
    assert course.timeslot_id == ts2.id


def test_solver_preference_overrides_stability(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # 1. Création Enseignant, Salle, Division, Créneaux
    t1 = Teacher(code="PROF_STAB", name="Prof Stab", last_name="Stab", school_id=school.id)
    t1._via_crud_mixin_create = True
    db_session.add(t1)
    db_session.commit()

    c1 = Classroom(code="ROOM_STAB", name="Room Stab", capacity=30, quantity=1, school_id=school.id)
    c1._via_crud_mixin_create = True
    db_session.add(c1)
    db_session.commit()

    d1 = Division(code="DIV_STAB", name="Div Stab", student_count=25, color="#CCCCCC", school_id=school.id)
    d1._via_crud_mixin_create = True
    db_session.add(d1)
    db_session.commit()

    ts1 = Timeslot(day_of_week=1, hour=8) # Position initiale (Neutre)
    ts2 = Timeslot(day_of_week=1, hour=9) # Préféré (Preferred)
    ts1._via_crud_mixin_create = True
    ts2._via_crud_mixin_create = True
    db_session.add_all([ts1, ts2])
    db_session.commit()

    # 2. Création du vœu "Preferred" sur ts2
    p1 = ResourcePreference(resource_type="Teacher", resource_id=t1.id, timeslot_id=ts2.id, preference_level="Preferred")
    p1._via_crud_mixin_create = True
    db_session.add(p1)
    db_session.commit()

    # 3. Création du cours initialement placé sur ts1 (déclenche la pénalité de stabilité s'il bouge)
    course = Course(
        subject_id=subject.id,
        teachers=[t1],
        divisions=[d1],
        classrooms=[c1],
        timeslot_id=ts1.id,
        school_id=school.id
    )
    course._via_crud_mixin_create = True
    db_session.add(course)
    db_session.commit()

    # 4. Résoudre
    _solve_timetable_job(db_session)
    db_session.refresh(course)

    # 5. Assertion : Le cours DOIT avoir bougé de ts1 à ts2 car la préférence (+10 soft) l'emporte sur la stabilité (-1 soft)
    assert course.timeslot_id is not None
    assert course.timeslot_id == ts2.id


def test_solver_respects_week_specific_preferences(db_session: Session):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # 1. Création Enseignant, Salle, Division, Créneaux
    t1 = Teacher(code="PROF_WEEK", name="Prof Week", last_name="Week", school_id=school.id)
    t1._via_crud_mixin_create = True
    db_session.add(t1)
    db_session.commit()

    c1 = Classroom(code="ROOM_WEEK", name="Room Week", capacity=30, quantity=1, school_id=school.id)
    c1._via_crud_mixin_create = True
    db_session.add(c1)
    db_session.commit()

    d1 = Division(code="DIV_WEEK", name="Div Week", student_count=25, color="#CCCCCC", school_id=school.id)
    d1._via_crud_mixin_create = True
    db_session.add(d1)
    db_session.commit()

    ts1 = Timeslot(day_of_week=1, hour=8) # Indisponible uniquement en semaine A (Unsuited)
    ts2 = Timeslot(day_of_week=1, hour=9) # Disponible (Neutre)
    ts1._via_crud_mixin_create = True
    ts2._via_crud_mixin_create = True
    db_session.add_all([ts1, ts2])
    db_session.commit()

    # 2. Création du vœu "Unsuited" uniquement en semaine A pour ts1
    p1 = ResourcePreference(resource_type="Teacher", resource_id=t1.id, timeslot_id=ts1.id, preference_level="Unsuited", week_type="A")
    p1._via_crud_mixin_create = True
    db_session.add(p1)
    db_session.commit()

    # 3. Création de deux cours : un pour la semaine A, un pour la semaine B
    course_a = Course(subject_id=subject.id, teachers=[t1], divisions=[d1], school_id=school.id)
    course_b = Course(subject_id=subject.id, teachers=[t1], divisions=[d1], school_id=school.id)
    course_a._via_crud_mixin_create = True
    course_b._via_crud_mixin_create = True
    db_session.add_all([course_a, course_b])
    db_session.commit()

    course_a.update(db_session, {"week_type": "A"})
    course_b.update(db_session, {"week_type": "B"})
    db_session.commit()

    # 4. Résoudre
    _solve_timetable_job(db_session)
    db_session.refresh(course_a)
    db_session.refresh(course_b)

    # 5. Assertions :
    # course_a (week_type='A') ne doit PAS être planifié sur ts1 car ts1 est Unsuited pour la semaine A.
    # course_b (week_type='B') PEUT être planifié sur ts1 car l'indisponibilité ne s'applique qu'à la semaine A.
    assert course_a.timeslot_id is not None
    assert course_b.timeslot_id is not None
    assert course_a.timeslot_id == ts2.id
    assert course_b.timeslot_id == ts1.id


def test_solver_respects_period_specific_preferences(db_session: Session, monkeypatch):
    school = db_session.query(School).first()
    subject = db_session.query(Subject).first()

    # 1. Création Enseignant, Salle, Division, Créneaux
    t1 = Teacher(code="PROF_PERIOD", name="Prof Period", last_name="Period", school_id=school.id)
    t1._via_crud_mixin_create = True
    db_session.add(t1)
    db_session.commit()

    c1 = Classroom(code="ROOM_PERIOD", name="Room Period", capacity=30, quantity=1, school_id=school.id)
    c1._via_crud_mixin_create = True
    db_session.add(c1)
    db_session.commit()

    d1 = Division(code="DIV_PERIOD", name="Div Period", student_count=25, color="#CCCCCC", school_id=school.id)
    d1._via_crud_mixin_create = True
    db_session.add(d1)
    db_session.commit()

    ts1 = Timeslot(day_of_week=1, hour=8) # Indisponible uniquement sur la période 1 (Unsuited)
    ts2 = Timeslot(day_of_week=1, hour=9) # Disponible
    ts1._via_crud_mixin_create = True
    ts2._via_crud_mixin_create = True
    db_session.add_all([ts1, ts2])
    db_session.commit()

    # 2. Création de deux périodes
    import datetime
    from backend.app.models.period_type import PeriodType
    pt = PeriodType(label="Semestre")
    pt._via_crud_mixin_create = True
    db_session.add(pt)
    db_session.commit()

    per1 = Period(period_type_id=pt.id, school_id=school.id, code="P1", name="Période 1", start_date=datetime.date(2026, 9, 1), end_date=datetime.date(2026, 12, 31))
    per2 = Period(period_type_id=pt.id, school_id=school.id, code="P2", name="Période 2", start_date=datetime.date(2027, 1, 1), end_date=datetime.date(2027, 6, 30))
    per1._via_crud_mixin_create = True
    per2._via_crud_mixin_create = True
    db_session.add_all([per1, per2])
    db_session.commit()

    # 3. Création du vœu "Unsuited" uniquement sur P1 pour ts1
    p1 = ResourcePreference(resource_type="Teacher", resource_id=t1.id, timeslot_id=ts1.id, preference_level="Unsuited")
    p1.periods.append(per1)
    p1._via_crud_mixin_create = True
    db_session.add(p1)
    db_session.commit()

    # 4. Création d'un cours
    course = Course(subject_id=subject.id, teachers=[t1], divisions=[d1], school_id=school.id)
    course._via_crud_mixin_create = True
    db_session.add(course)
    db_session.commit()

    # Cas 1 : Pas d'intersection (Cours sur P2 uniquement)
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
    
    # Le cours doit être planifié sur ts1 car sans chevauchement avec P1, le vœu Unsuited est inactif.
    assert course.timeslot_id == ts1.id

    # Cas 2 : Intersection (Cours sur P1 uniquement)
    def patched_build_overlap(db, school_id=None):
        problem = original_build(db, school_id)
        for pc in problem.courses:
            if pc.id == course.id:
                pc.period_ids = [per1.id]
        return problem

    monkeypatch.setattr(solver, "_build_planning_problem", patched_build_overlap)

    # Réinitialiser le timeslot
    course.update(db_session, {"timeslot_id": None})
    db_session.commit()

    _solve_timetable_job(db_session)
    db_session.refresh(course)

    # Le cours doit être planifié sur ts2 car le vœu Unsuited s'applique par intersection de périodes.
    assert course.timeslot_id == ts2.id



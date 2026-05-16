from sqlalchemy.orm import Session
from timefold.solver import SolverFactory
from timefold.solver.config import SolverConfig, TerminationConfig, ScoreDirectorFactoryConfig, Duration, EnvironmentMode
from backend.app.core.config import settings
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.solver.constraints import (
    PlanningTeacher,
    PlanningClassroom,
    PlanningDivision,
    PlanningTimeslot,
    PlanningCourse,
    PlanningTimetable,
    define_constraints,
)


class UnsolvableTimetableException(Exception):
    """Exception levée lorsque le solveur Timefold ne trouve aucune solution valide sans conflits."""
    pass


def solve_timetable(db: Session):
    # 1. Charger toutes les données depuis la base de données SQLite
    db_teachers = db.query(Teacher).all()
    db_classrooms = db.query(Classroom).all()
    db_divisions = db.query(Division).all()
    db_timeslots = db.query(Timeslot).all()
    db_courses = db.query(Course).all()

    # 2. Mapper les entités vers les classes de planification Timefold
    # Création des dictionnaires pour des correspondances ultra-rapides
    teachers_map = {t.id: PlanningTeacher(t.id, t.name) for t in db_teachers}
    classrooms_map = {c.id: PlanningClassroom(c.id, c.name, c.capacity) for c in db_classrooms}
    divisions_map = {d.id: PlanningDivision(d.id, d.name) for d in db_divisions}
    timeslots_map = {ts.id: PlanningTimeslot(ts.id, ts.day_of_week, ts.hour) for ts in db_timeslots}

    # Liste des faits de planification (Planning Facts)
    teachers_list = list(teachers_map.values())
    classrooms_list = list(classrooms_map.values())
    divisions_list = list(divisions_map.values())
    timeslots_list = list(timeslots_map.values())

    # Mapper les cours (Planning Entities)
    courses_list = []
    for c in db_courses:
        # Récupérer les correspondances si déjà planifié
        ts_planning = timeslots_map.get(c.timeslot_id) if c.timeslot_id else None
        cr_planning = classrooms_map.get(c.classroom_id) if c.classroom_id else None
        
        pc = PlanningCourse(
            id=c.id,
            subject=c.subject,
            teacher=teachers_map[c.teacher_id],
            division=divisions_map[c.division_id],
            timeslot=ts_planning,
            classroom=cr_planning,
            is_pinned=c.is_pinned,
        )
        courses_list.append(pc)

    # 3. Construire le problème de départ (Planning Problem Solution)
    problem = PlanningTimetable(
        teachers=teachers_list,
        classrooms=classrooms_list,
        divisions=divisions_list,
        timeslots=timeslots_list,
        courses=courses_list,
        score=None,
    )

    # 4. Configurer le solveur Timefold avec le ConstraintProvider déclaratif
    limit_seconds = settings.SOLVER_TIME_LIMIT_SECONDS
    solver_config = SolverConfig(
        environment_mode=EnvironmentMode.NO_ASSERT,
        solution_class=PlanningTimetable,
        entity_class_list=[PlanningCourse],
        score_director_factory_config=ScoreDirectorFactoryConfig(
            constraint_provider_function=define_constraints
        ),
        termination_config=TerminationConfig(
            spent_limit=Duration(seconds=limit_seconds)
        ),
    )

    solver_factory = SolverFactory.create(solver_config)
    solver = solver_factory.build_solver()

    # 5. Lancer la résolution avec le solveur Timefold
    try:
        solution = solver.solve(problem)
    except Exception as e:
        # En cas d'erreur ou timeout, on conserve le problème initial
        solution = problem

    # 6. Mettre à jour les enregistrements en base de données avec la solution optimale trouvée par Timefold
    for pc in solution.courses:
        db_course = db.query(Course).filter(Course.id == pc.id).first()
        if db_course:
            db_course.timeslot_id = pc.timeslot.id if pc.timeslot else None
            db_course.classroom_id = pc.classroom.id if pc.classroom else None

    # Valider la transaction dans la base de données
    db.commit()

from sqlalchemy.orm import Session
from timefold.solver import SolverFactory
from timefold.solver.config import SolverConfig, TerminationConfig, ScoreDirectorFactoryConfig, Duration, EnvironmentMode
from backend.app.core.config import settings
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.core.database import SessionLocal
import threading
from backend.app.solver.constraints import (
    PlanningTeacher,
    PlanningClassroom,
    PlanningDivision,
    PlanningTimeslot,
    PlanningCourse,
    PlanningTimetable,
    define_constraints,
)


class SolverState:
    _lock = threading.Lock()
    active_solver = None
    status = "NOT_SOLVING"

    @classmethod
    def set_solving(cls, solver):
        with cls._lock:
            cls.active_solver = solver
            cls.status = "SOLVING"

    @classmethod
    def set_not_solving(cls):
        with cls._lock:
            cls.active_solver = None
            cls.status = "NOT_SOLVING"

    @classmethod
    def get_status(cls):
        with cls._lock:
            return cls.status

    @classmethod
    def stop_solving(cls):
        with cls._lock:
            if cls.active_solver is not None:
                try:
                    cls.active_solver.terminate_early()
                except Exception:
                    pass


def _solve_timetable_job(db_session=None):
    db = db_session if db_session else SessionLocal()
    try:
        # 1. Charger toutes les données depuis la base de données SQLite
        db_teachers = db.query(Teacher).all()
        db_classrooms = db.query(Classroom).all()
        db_divisions = db.query(Division).all()
        db_timeslots = db.query(Timeslot).all()
        db_courses = db.query(Course).all()

        teachers_map = {t.id: PlanningTeacher(t.id, t.name) for t in db_teachers}
        classrooms_map = {c.id: PlanningClassroom(c.id, c.name, c.capacity) for c in db_classrooms}
        divisions_map = {d.id: PlanningDivision(d.id, d.name) for d in db_divisions}
        timeslots_map = {ts.id: PlanningTimeslot(ts.id, ts.day_of_week, ts.hour) for ts in db_timeslots}

        teachers_list = list(teachers_map.values())
        classrooms_list = list(classrooms_map.values())
        divisions_list = list(divisions_map.values())
        timeslots_list = list(timeslots_map.values())

        courses_list = []
        for c in db_courses:
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

        problem = PlanningTimetable(
            teachers=teachers_list,
            classrooms=classrooms_list,
            divisions=divisions_list,
            timeslots=timeslots_list,
            courses=courses_list,
            score=None,
        )

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

        # Enregistrer le solveur actif
        SolverState.set_solving(solver)

        try:
            solution = solver.solve(problem)
        except Exception:
            solution = problem
        finally:
            SolverState.set_not_solving()

        # Mettre à jour les enregistrements
        for pc in solution.courses:
            db_course = db.query(Course).filter(Course.id == pc.id).first()
            if db_course:
                db_course.timeslot_id = pc.timeslot.id if pc.timeslot else None
                db_course.classroom_id = pc.classroom.id if pc.classroom else None

        db.commit()

    except Exception as e:
        db.rollback()
        print(f"Solver thread error: {e}")
    finally:
        if not db_session:
            db.close()
        SolverState.set_not_solving()


def start_solve_timetable_async():
    if SolverState.get_status() == "SOLVING":
        return
    thread = threading.Thread(target=_solve_timetable_job)
    thread.daemon = True
    thread.start()

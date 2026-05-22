from typing import Optional
from sqlalchemy.orm import Session
from timefold.solver import SolverFactory
from timefold.solver.config import SolverConfig, TerminationConfig, ScoreDirectorFactoryConfig, Duration, EnvironmentMode
from timefold.solver import SolutionManager
from backend.app.core.config import settings
from backend.app.models.teacher import Teacher
from backend.app.models.non_teaching_staff import NonTeachingStaff
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.models.group import ClassPartLink
from backend.app.models.preference import ResourcePreference
from backend.app.models.constraint import ResourceConstraint
from backend.app.models.period import Period
from backend.app.core.database import SessionLocal
import threading
from backend.app.solver.constraints import (
    PlanningTeacher,
    PlanningNonTeachingStaff,
    PlanningClassroom,
    PlanningDivision,
    PlanningTimeslot,
    PlanningCourse,
    PlanningClassPartLink,
    PlanningPreference,
    PlanningResourceConstraint,
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
            if cls.active_solver:
                try:
                    cls.active_solver.terminate_early()
                except Exception:
                    pass


def _build_planning_problem(db: Session, school_id: Optional[int] = None) -> PlanningTimetable:
    db_teachers = db.query(Teacher).all()
    db_non_teaching_staffs = db.query(NonTeachingStaff).all()
    db_classrooms = db.query(Classroom).all()
    db_divisions = db.query(Division).all()
    
    from backend.app.models.system_setting import SystemSetting
    setting = db.query(SystemSetting).filter(SystemSetting.key == "STANDARD_TIMESLOT_DURATION").first()
    if not setting or not setting.value.isdigit():
        raise ValueError("Le paramètre système 'STANDARD_TIMESLOT_DURATION' est manquant ou invalide.")
    duration = int(setting.value)
    
    step = duration / 60.0
    db_timeslots = db.query(Timeslot).all()
    db_timeslots = [
        ts for ts in db_timeslots 
        if abs((ts.hour / step) - round(ts.hour / step)) < 0.001
    ]
    
    # IMPORTANT : Le solveur ne travaille QUE sur les cours de premier niveau.
    # Les cours simples enfants (qui subdivisent un cours composé) sont uniquement
    # utilisés pour l'affichage et le détail des ressources. Le placement global sur
    # la grille horaire est géré exclusivement au niveau du cours parent.
    db_courses = db.query(Course).filter(Course.parent_id == None).all()
    db_links = db.query(ClassPartLink).all()
    db_preferences = db.query(ResourcePreference).all()
    db_constraints = db.query(ResourceConstraint).all()
    db_periods = db.query(Period).all()

    teachers_map = {t.id: PlanningTeacher(t.id, t.name) for t in db_teachers}
    non_teaching_staffs_map = {s.id: PlanningNonTeachingStaff(s.id, s.first_name, s.last_name) for s in db_non_teaching_staffs}
    classrooms_map = {c.id: PlanningClassroom(c.id, c.name, c.capacity) for c in db_classrooms}
    divisions_map = {d.id: PlanningDivision(d.id, d.name) for d in db_divisions}
    timeslots_map = {ts.id: PlanningTimeslot(ts.id, ts.day_of_week, ts.hour) for ts in db_timeslots}

    teachers_list = list(teachers_map.values())
    non_teaching_staffs_list = list(non_teaching_staffs_map.values())
    classrooms_list = list(classrooms_map.values())
    divisions_list = list(divisions_map.values())
    timeslots_list = list(timeslots_map.values())
    links_list = [PlanningClassPartLink(link.class_part_a_id, link.class_part_b_id) for link in db_links]
    preferences_list = [
        PlanningPreference(
            id=pref.id,
            resource_type=pref.resource_type,
            resource_id=pref.resource_id,
            timeslot_id=pref.timeslot_id,
            preference_level=pref.preference_level,
            week_type=pref.week_type,
            period_ids=[p.id for p in pref.periods]
        ) for pref in db_preferences
    ]
    constraints_list = [
        PlanningResourceConstraint(
            id=rc.id,
            resource_type=rc.resource_type,
            resource_id=rc.resource_id,
            target_subject_b_id=rc.target_subject_b_id,
            incompatible_same_half_day=rc.incompatible_same_half_day,
            incompatible_same_day=rc.incompatible_same_day,
            incompatible_two_consecutive_days=rc.incompatible_two_consecutive_days,
            min_free_half_days_between=rc.min_free_half_days_between,
            prevent_consecutive_a_then_b=rc.prevent_consecutive_a_then_b,
            prevent_consecutive_b_then_a=rc.prevent_consecutive_b_then_a,
            max_hours_per_day=rc.max_hours_per_day,
            max_hours_per_half_day=rc.max_hours_per_half_day,
            weekly_order_a_before_b=rc.weekly_order_a_before_b,
            weekly_order_b_before_a=rc.weekly_order_b_before_a,
            group_course_order=rc.group_course_order,
            max_hours_per_am=rc.max_hours_per_am,
            max_hours_per_pm=rc.max_hours_per_pm,
            max_presence_days_per_week=rc.max_presence_days_per_week,
            max_presence_hours_per_day=rc.max_presence_hours_per_day,
            late_start_days_per_week=rc.late_start_days_per_week,
            late_start_time=rc.late_start_time,
            early_end_days_per_week=rc.early_end_days_per_week,
            early_end_time=rc.early_end_time,
            min_free_days_per_week=rc.min_free_days_per_week,
            min_free_half_days_per_week=rc.min_free_half_days_per_week,
            max_worked_am_per_week=rc.max_worked_am_per_week,
            max_worked_pm_per_week=rc.max_worked_pm_per_week,
            only_one_half_day_per_day=rc.only_one_half_day_per_day,
            max_gap_hours_per_week=rc.max_gap_hours_per_week or 2
        ) for rc in db_constraints
    ]

    courses_list = []
    for c in db_courses:
        ts_planning = timeslots_map.get(c.timeslot_id) if c.timeslot_id else None
        cr_planning = classrooms_map.get(c.classrooms[0].id) if c.classrooms else None
        
        # Gestion multi-établissement (US2) :
        # Si school_id est spécifié et que ce cours appartient à une AUTRE école,
        # il est forcé à is_pinned = True pour ne pas être déplacé par le solveur
        is_pinned = c.is_pinned
        if school_id is not None and c.school_id != school_id:
            is_pinned = True
            
        # Charger week_type et class_part_ids
        week_type = c.effective_week_type
        class_part_ids = []
            
        if c.groups:
            for grp in c.groups:
                class_part_ids.extend([cp.id for cp in grp.class_parts])
        if c.divisions:
            for div in c.divisions:
                class_part_ids.extend([cp.id for cp in div.class_parts])
            
        if c.class_parts:
            class_part_ids.extend([cp.id for cp in c.class_parts])
        if c.groups:
            for grp in c.groups:
                class_part_ids.extend([cp.id for cp in grp.class_parts])
                    
        class_part_ids = list(set(class_part_ids))
            
        pc = PlanningCourse(
            id=c.id,
            subject=c.subject,
            teachers=[teachers_map[t.id] for t in c.teachers if t.id in teachers_map],
            non_teaching_staffs=[non_teaching_staffs_map[s.id] for s in c.non_teaching_staffs if s.id in non_teaching_staffs_map],
            divisions=[divisions_map[d.id] for d in c.divisions if d.id in divisions_map],
            timeslot=ts_planning,
            classroom=cr_planning,
            is_pinned=is_pinned,
            original_timeslot_id=c.timeslot_id,
            parent_id=getattr(c, 'parent_id', None),
            week_type=week_type,
            class_part_ids=class_part_ids,
            period_ids=[getattr(c, 'period_id')] if getattr(c, 'period_id', None) else [p.id for p in db_periods],
            step=c.duration_minutes / 60.0
        )
        courses_list.append(pc)

    return PlanningTimetable(
        teachers=teachers_list,
        non_teaching_staffs=non_teaching_staffs_list,
        classrooms=classrooms_list,
        divisions=divisions_list,
        timeslots=timeslots_list,
        courses=courses_list,
        class_part_links=links_list,
        preferences=preferences_list,
        resource_constraints=constraints_list,
        score=None,
    )

def _get_solver_factory():
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
    return SolverFactory.create(solver_config)

def _solve_timetable_job(db_session=None, school_id=None):
    db = db_session if db_session else SessionLocal()
    try:
        problem = _build_planning_problem(db, school_id)
        solver_factory = _get_solver_factory()
        solver = solver_factory.build_solver()

        # Enregistrer le solveur actif
        SolverState.set_solving(solver)

        try:
            solution = solver.solve(problem)
        finally:
            SolverState.set_not_solving()

        # Mettre à jour les enregistrements
        for pc in solution.courses:
            db_course = db.query(Course).filter(Course.id == pc.id).first()
            if db_course:
                db_course._via_crud_mixin_update = True
                db_course.timeslot_id = pc.timeslot.id if pc.timeslot else None
                if pc.classroom:
                    db_classroom = db.query(Classroom).get(pc.classroom.id)
                    if db_classroom:
                        db_course.classrooms = [db_classroom]
                else:
                    db_course.classrooms = []

        db.commit()

    except Exception as e:
        db.rollback()
        print(f"Solver thread error: {e}")
    finally:
        if not db_session:
            db.close()
        SolverState.set_not_solving()


def start_solve_timetable_async(school_id: Optional[int] = None):
    if SolverState.get_status() == "SOLVING":
        return
    thread = threading.Thread(target=_solve_timetable_job, kwargs={"school_id": school_id})
    thread.daemon = True
    thread.start()

def explain_timetable_score(db: Session, school_id: Optional[int] = None) -> dict:
    problem = _build_planning_problem(db, school_id)
    solver_factory = _get_solver_factory()
    solution_manager = SolutionManager.create(solver_factory)
    score_explanation = solution_manager.explain(problem)
    score = score_explanation.score
    
    matches_detail = {}
    for cmt in score_explanation.constraint_match_total_map.values():
        matches_detail[cmt.constraint_ref.constraint_name] = {
            "hard": cmt.score.hard_score if hasattr(cmt.score, 'hard_score') else 0,
            "soft": cmt.score.soft_score if hasattr(cmt.score, 'soft_score') else 0,
            "count": len(cmt.constraint_match_set)
        }

    return {
        "hard_score": score.hard_score if score else 0,
        "soft_score": score.soft_score if score else 0,
        "summary": score_explanation.summary,
        "matches": matches_detail
    }

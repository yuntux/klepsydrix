from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
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
from backend.app.models.constraint import ResourceConstraint, CourseToCourseConstraint, SubjectToSubjectConstraint
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
    PlanningCourseToCourseConstraint,
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
    def set_solving_status(cls):
        with cls._lock:
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
    db_teachers = db.execute(select(Teacher)).scalars().unique().all()
    db_non_teaching_staffs = db.execute(select(NonTeachingStaff)).scalars().unique().all()
    db_classrooms = db.execute(select(Classroom)).scalars().unique().all()
    db_divisions = db.execute(select(Division)).scalars().unique().all()
    
    db_timeslots = Timeslot.get_active_timeslots(db)
    
    # IMPORTANT : Le solveur ne travaille QUE sur les cours de premier niveau.
    # Les cours simples enfants (qui subdivisent un cours composé) sont uniquement
    # utilisés pour l'affichage et le détail des ressources. Le placement global sur
    # la grille horaire est géré exclusivement au niveau du cours parent.
    db_courses = db.execute(select(Course).filter(Course.parent_id == None)).scalars().unique().all()
    db_links = db.execute(select(ClassPartLink)).scalars().unique().all()
    db_preferences = db.execute(select(ResourcePreference)).scalars().unique().all()
    db_constraints = db.execute(select(ResourceConstraint)).scalars().unique().all()
    db_course_constraints = db.execute(select(CourseToCourseConstraint)).scalars().unique().all()
    db_periods = db.execute(select(Period)).scalars().unique().all()

    teachers_map = {t.id: PlanningTeacher(t.id, t.display_name) for t in db_teachers}
    non_teaching_staffs_map = {s.id: PlanningNonTeachingStaff(s.id, s.first_name, s.last_name) for s in db_non_teaching_staffs}
    classrooms_map = {c.id: PlanningClassroom(c.id, c.name, c.capacity) for c in db_classrooms}
    from backend.app.models.school import School
    sch_limits = {}
    if school_id is not None:
        school_obj = db.execute(select(School).filter(School.id == school_id)).scalars().first()
        if school_obj:
            sch_limits["day"] = school_obj.max_pedagogic_weight_per_day
            sch_limits["morning"] = school_obj.max_pedagogic_weight_per_morning
            sch_limits["afternoon"] = school_obj.max_pedagogic_weight_per_afternoon

    divisions_map = {d.id: PlanningDivision(
        id=d.id,
        name=d.name,
        max_pedagogic_weight_per_day=sch_limits.get("day"),
        max_pedagogic_weight_per_morning=sch_limits.get("morning"),
        max_pedagogic_weight_per_afternoon=sch_limits.get("afternoon")
    ) for d in db_divisions}
    from backend.app.models.system_setting import SystemSetting, SystemSettingKey
    setting = db.execute(select(SystemSetting).filter(SystemSetting.key == SystemSettingKey.STANDARD_TIMESLOT_DURATION)).scalars().first()
    if not setting or not setting.value:
        raise ValueError("Le paramètre système obligatoire 'STANDARD_TIMESLOT_DURATION' est manquant ou non défini.")
    std_duration_min = int(setting.value)
    
    max_minutes_by_day = {}
    for ts in db_timeslots:
        if ts.day_of_week not in max_minutes_by_day or ts.minutes_from_midnight > max_minutes_by_day[ts.day_of_week]:
            max_minutes_by_day[ts.day_of_week] = ts.minutes_from_midnight

    timeslots_map = {ts.id: PlanningTimeslot(ts.id, ts.day_of_week, ts.minutes_from_midnight, max_minutes_by_day[ts.day_of_week] + std_duration_min, ts.get_noon_boundary_minutes()) for ts in db_timeslots}

    teachers_list = list(teachers_map.values())
    non_teaching_staffs_list = list(non_teaching_staffs_map.values())
    classrooms_list = list(classrooms_map.values())
    divisions_list = list(divisions_map.values())
    timeslots_list = list(timeslots_map.values())
    links_list = [PlanningClassPartLink(link.class_part_a_id, link.class_part_b_id) for link in db_links]
    period_to_bit = {p.id: (1 << i) for i, p in enumerate(db_periods)}

    preferences_list = [
        PlanningPreference(
            id=pref.id,
            resource_type=pref.resource_type,
            resource_id=pref.resource_id,
            timeslot_id=pref.timeslot_id,
            preference_level=pref.preference_level,
            week_type=pref.week_type,
            period_ids=[p.id for p in pref.periods],
            period_mask=sum(period_to_bit.get(p.id, 0) for p in pref.periods)
        ) for pref in db_preferences
    ]
    constraints_list = [
        PlanningResourceConstraint(
            id=rc.id,
            resource_type=rc.resource_type,
            resource_id=rc.resource_id,
            is_optional=rc.is_optional,
            target_subject_b_id=rc.target_subject_b_id,
            incompatible_same_half_day=bool(rc.incompatible_same_half_day),
            incompatible_same_day=bool(rc.incompatible_same_day),
            incompatible_two_consecutive_days=bool(rc.incompatible_two_consecutive_days),
            min_free_half_days_between=rc.min_free_half_days_between,
            prevent_consecutive_a_then_b=bool(rc.prevent_consecutive_a_then_b),
            prevent_consecutive_b_then_a=bool(rc.prevent_consecutive_b_then_a),
            max_hours_per_day=rc.max_hours_per_day,
            max_hours_per_half_day=rc.max_hours_per_half_day,
            weekly_order=rc.weekly_order.value if rc.weekly_order else "NONE",
            group_course_order=rc.group_course_order.value if rc.group_course_order else "NONE",
            max_separation=rc.max_separation.value if rc.max_separation else "NONE",
            division_ids=[d.id for d in rc.divisions] if rc.divisions else [],
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
            only_one_half_day_per_day=bool(rc.only_one_half_day_per_day),
            max_gap_hours_per_week=rc.max_gap_hours_per_week or 2
        ) for rc in db_constraints
    ] + [
        PlanningResourceConstraint(
            id=-rc.id,
            resource_type="Subject",
            resource_id=rc.target_subject_a_id,
            target_subject_a_id=rc.target_subject_a_id,
            is_optional=rc.is_optional,
            target_subject_b_id=rc.target_subject_b_id,
            incompatible_same_half_day=bool(rc.incompatible_same_half_day),
            incompatible_same_day=bool(rc.incompatible_same_day),
            incompatible_two_consecutive_days=bool(rc.incompatible_two_consecutive_days),
            min_free_half_days_between=rc.min_free_half_days_between,
            prevent_consecutive_a_then_b=bool(rc.prevent_consecutive_a_then_b),
            prevent_consecutive_b_then_a=bool(rc.prevent_consecutive_b_then_a),
            max_hours_per_day=rc.max_hours_per_day,
            max_hours_per_half_day=rc.max_hours_per_half_day,
            weekly_order=rc.weekly_order.value if rc.weekly_order else "NONE",
            group_course_order=rc.group_course_order.value if rc.group_course_order else "NONE",
            max_separation=rc.max_separation.value if rc.max_separation else "NONE",
            division_ids=[d.id for d in rc.divisions] if rc.divisions else [],
            max_hours_per_am=None,
            max_hours_per_pm=None,
            max_presence_days_per_week=None,
            max_presence_hours_per_day=None,
            late_start_days_per_week=None,
            late_start_time=None,
            early_end_days_per_week=None,
            early_end_time=None,
            min_free_days_per_week=None,
            min_free_half_days_per_week=None,
            max_worked_am_per_week=None,
            max_worked_pm_per_week=None,
            only_one_half_day_per_day=False,
            max_gap_hours_per_week=2
        ) for rc in db.execute(select(SubjectToSubjectConstraint)).scalars().unique().all()
    ]

    course_constraints_list = [
        PlanningCourseToCourseConstraint(
            id=cc.id,
            type=cc.type,
            scope=cc.scope or "SLOT",
            custom_half_days=cc.custom_half_days,
            course_ids=[c.id for c in cc.courses],
            is_optional=cc.is_optional,
            label=cc.label
        ) for cc in db_course_constraints
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
        week_type = c.week_type.value
        class_part_ids = []
        division_ids = set([d.id for d in c.divisions]) if c.divisions else set()
            
        if c.groups:
            for grp in c.groups:
                for cp in grp.class_parts:
                    class_part_ids.append(cp.id)
                    if cp.division_id:
                        division_ids.add(cp.division_id)
        if c.divisions:
            for div in c.divisions:
                for part in div.partitions:
                    class_part_ids.extend([cp.id for cp in part.class_parts])
            
        if c.class_parts:
            for cp in c.class_parts:
                class_part_ids.append(cp.id)
                if cp.division_id:
                    division_ids.add(cp.division_id)
                    
        class_part_ids = list(set(class_part_ids))
            
        from backend.app.models.subject import Subject
        pedagogic_weight = 0.0
        if c.subject_id:
            subj = db.execute(select(Subject).filter(Subject.id == c.subject_id)).scalars().first()
            if subj and subj.pedagogic_weight:
                pedagogic_weight = subj.pedagogic_weight

        p_ids = (
            [p.id for p in c.periods]
            if c.periods
            else (
                [p.id for p in db_periods if p.period_type_id == c.period_type_id]
                if c.period_type_id
                else [p.id for p in db_periods]
            )
        )
        pc = PlanningCourse(
            id=c.id,
            subject_id=c.subject_id,
            teachers=[teachers_map[t.id] for t in c.teachers if t.id in teachers_map],
            non_teaching_staffs=[non_teaching_staffs_map[s.id] for s in c.non_teaching_staffs if s.id in non_teaching_staffs_map],
            divisions=[divisions_map[d.id] for d in c.divisions if d.id in divisions_map],
            timeslot=ts_planning,
            classroom=cr_planning,
            is_pinned=is_pinned,
            original_timeslot_id=c.timeslot_id,
            original_classroom_id=cr_planning.id if cr_planning else None,
            parent_id=getattr(c, 'parent_id', None),
            pedagogic_weight_total=pedagogic_weight * (c.duration_minutes / 60.0),
            week_type=week_type,
            class_part_ids=class_part_ids,
            all_division_ids=list(division_ids),
            is_full_class=(len(c.divisions) > 0 and len(c.groups) == 0 and len(c.class_parts) == 0),
            period_ids=p_ids,
            period_mask=sum(period_to_bit.get(pid, 0) for pid in p_ids),
            duration_minutes=c.duration_minutes
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
        course_to_course_constraints=course_constraints_list,
        score=None,
    )

def _get_solver_factory():
    limit_seconds = settings.SOLVER_TIME_LIMIT_SECONDS
    unimproved_limit_seconds = settings.SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS
    solver_config = SolverConfig(
        environment_mode=EnvironmentMode.NO_ASSERT,
        solution_class=PlanningTimetable,
        entity_class_list=[PlanningCourse],
        score_director_factory_config=ScoreDirectorFactoryConfig(
            constraint_provider_function=define_constraints
        ),
        termination_config=TerminationConfig(
            spent_limit=Duration(seconds=limit_seconds),
            unimproved_spent_limit=Duration(seconds=unimproved_limit_seconds)
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
        # ATTENTION ARCHITECTURE : Le solveur n'appelle JAMAIS la méthode Course.update() du CRUDMixin
        # pour des raisons de performances (éviter de déclencher des milliers de validations Pydantic/Python).
        # Il assigne directement les attributs (Direct Attribute Assignment) et fait un db.commit() brut.
        # CONSÉQUENCE : Toute règle métier vérifiée dans `Course.validate_placement_conflicts()` 
        # (ex: débordement de grille) DOIT obligatoirement être dupliquée en tant que contrainte Timefold
        # dans `constraints.py`, sinon l'IA contournera la sécurité lors de la sauvegarde.
        for pc in solution.courses:
            db_course = db.get(Course, pc.id)
            if db_course:
                db_course._via_crud_mixin_update = True
                db_course.timeslot_id = pc.timeslot.id if pc.timeslot else None
                if not db_course.is_composed:
                    if pc.classroom:
                        db_classroom = db.get(Classroom, pc.classroom.id)
                        if db_classroom:
                            db_course.classrooms = [db_classroom]
                    else:
                        db_course.classrooms = []
                else:
                    # Synchroniser le timeslot de chaque cours enfant par rapport au parent
                    from backend.app.models.timeslot import Timeslot
                    parent_ts = db.get(Timeslot, db_course.timeslot_id) if db_course.timeslot_id else None
                    for child in db_course.children:
                        child._via_crud_mixin_update = True
                        if parent_ts:
                            child.timeslot_id = parent_ts.get_offset_timeslot(db, child.parent_timeslot_offset)
                        else:
                            child.timeslot_id = None
                        child.recompute_status()
                
                db_course.recompute_status()

        db.commit()
        return solution

    except Exception as e:
        db.rollback()
        print(f"Solver thread error: {e}")
        raise e
    finally:
        if not db_session:
            db.close()
        SolverState.set_not_solving()


def start_solve_timetable_async(school_id: Optional[int] = None):
    if SolverState.get_status() == "SOLVING":
        return
    SolverState.set_solving_status()
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

    # Calcul d'un score soft épuré de la pénalité artificielle d'Overconstrained Planning
    original_soft_score = score.soft_score if score else 0
    unassigned_constraint_name = "Pénaliser les cours non assignés (Overconstrained Planning)"
    unassigned_soft_impact = 0
    if unassigned_constraint_name in matches_detail:
        unassigned_soft_impact = matches_detail[unassigned_constraint_name]["soft"]
        
    clean_soft_score = original_soft_score - unassigned_soft_impact

    return {
        "hard_score": score.hard_score if score else 0,
        "soft_score": clean_soft_score,
        "summary": score_explanation.summary,
        "matches": matches_detail
    }

def calculate_course_heatmap(db: Session, course_id: int, school_id: Optional[int] = None) -> dict:
    problem = _build_planning_problem(db, school_id)
    solver_factory = _get_solver_factory()
    
    # --- EXPERIMENTAL JAVA HOOK ---
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
    
    try:
        from backend.experimental_java_heatmap.heatmap_proxy import calculate_heatmap_java
        return calculate_heatmap_java(problem, solver_factory, course_id)
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}
    # ------------------------------
    
    """
    solution_manager = SolutionManager.create(solver_factory)
    
    # Trouver le cours concerné
    target_course = next((c for c in problem.courses if c.id == course_id), None)
    if not target_course:
        return {}
        
    original_timeslot = target_course.timeslot
    heatmap = {}
    
    # Calculer le score de base sans le cours
    target_course.timeslot = None
    base_explanation = solution_manager.explain(problem)
    base_hard = base_explanation.score.hard_score if hasattr(base_explanation.score, 'hard_score') else 0
    base_soft = base_explanation.score.soft_score if hasattr(base_explanation.score, 'soft_score') else 0

    for ts in problem.timeslots:
        target_course.timeslot = ts
        # Utiliser update() pour être ultra rapide sur les créneaux verts
        score = solution_manager.update(problem)
        
        current_hard = score.hard_score if hasattr(score, 'hard_score') else 0
        current_soft = score.soft_score if hasattr(score, 'soft_score') else 0
        
        delta_hard = current_hard - base_hard
        delta_soft = current_soft - base_soft
        
        reasons = []
        # N'expliquer que s'il y a une dégradation (pour la performance)
        if delta_hard < 0 or delta_soft < 0:
            explanation = solution_manager.explain(problem)
            for constraint_name, cmt in explanation.constraint_match_total_map.items():
                base_cmt = base_explanation.constraint_match_total_map.get(constraint_name)
                
                cur_hard = cmt.score.hard_score if hasattr(cmt.score, 'hard_score') else 0
                cur_soft = cmt.score.soft_score if hasattr(cmt.score, 'soft_score') else 0
                
                b_hard = base_cmt.score.hard_score if base_cmt and hasattr(base_cmt.score, 'hard_score') else 0
                b_soft = base_cmt.score.soft_score if base_cmt and hasattr(base_cmt.score, 'soft_score') else 0
                
                diff_hard = cur_hard - b_hard
                diff_soft = cur_soft - b_soft
                
                # Si cette contrainte s'est aggravée par rapport au score de base
                if diff_hard < 0 or diff_soft < 0:
                    reasons.append({
                        "name": cmt.constraint_ref.constraint_name,
                        "impact_hard": diff_hard,
                        "impact_soft": diff_soft
                    })
                    
        heatmap[str(ts.id)] = {
            "hard": delta_hard,
            "soft": delta_soft,
            "reasons": reasons
        }
        
    # Remettre à l'état initial
    target_course.timeslot = original_timeslot
    
    return heatmap
    """

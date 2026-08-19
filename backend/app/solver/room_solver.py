"""
Construction du problème, write-back et cache de SolverFactory pour le domaine
CLASSROOM_ASSIGNMENT (voir plan salles §3.4). Séparé de solver.py (COURSE_PLACEMENT) — même
raisonnement de séparation que constraints.py/room_constraints.py.
"""
import threading
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from timefold.solver import SolverFactory
from timefold.solver.config import SolverConfig, ScoreDirectorFactoryConfig, EnvironmentMode

from backend.app.models.course import Course
from backend.app.models.classroom import Classroom
from backend.app.models.course_classroom_requirement import CourseClassroomRequirement
from backend.app.models.preference import ResourcePreference
from backend.app.models.classroom_closure import leaf_classroom_ids_under
from backend.app.solver.constraints import PlanningClassroom, PlanningPreference
from backend.app.solver.room_constraints import (
    PlanningRoomAssignment,
    PlanningFixedRoomBooking,
    PlanningRoomOptimizationSettings,
    PlanningRoomTimetable,
    define_room_constraints,
)

_ROOM_SOLVER_FACTORY_CACHE = None
_ROOM_SOLVER_FACTORY_LOCK = threading.Lock()


def _get_classroom_assignment_solver_factory():
    global _ROOM_SOLVER_FACTORY_CACHE
    if _ROOM_SOLVER_FACTORY_CACHE is None:
        with _ROOM_SOLVER_FACTORY_LOCK:
            if _ROOM_SOLVER_FACTORY_CACHE is None:
                solver_config = SolverConfig(
                    environment_mode=EnvironmentMode.NO_ASSERT,
                    solution_class=PlanningRoomTimetable,
                    entity_class_list=[PlanningRoomAssignment],
                    score_director_factory_config=ScoreDirectorFactoryConfig(
                        constraint_provider_function=define_room_constraints
                    ),
                )
                _ROOM_SOLVER_FACTORY_CACHE = SolverFactory.create(solver_config)
    return _ROOM_SOLVER_FACTORY_CACHE


def _effective_timeslot_and_fields(db: Session, course: Course):
    """
    Timeslot effectif d'un cours (parent ou enfant, voir plan salles §3.1) : celui du cours
    lui-même s'il en a un, sinon celui de son parent décalé de parent_timeslot_offset (voir
    Timeslot.get_offset_timeslot, déjà utilisé par le write-back COURSE_PLACEMENT pour la même
    raison). Retourne None si aucun timeslot résolu (ni le cours, ni son parent) — la ligne doit
    alors être exclue du domaine.
    """
    from backend.app.models.timeslot import Timeslot

    if course.timeslot_id:
        return db.get(Timeslot, course.timeslot_id)
    if course.parent_id:
        parent = course.parent
        if parent and parent.timeslot_id:
            parent_ts = db.get(Timeslot, parent.timeslot_id)
            if parent_ts:
                offset_ts_id = parent_ts.get_offset_timeslot(db, course.parent_timeslot_offset)
                if offset_ts_id:
                    return db.get(Timeslot, offset_ts_id)
    return None


def _effective_headcount(course: Course) -> Optional[int]:
    """Somme des effectifs des ressources d'audience du cours (division/groupe) — None si le
    cours n'a ni l'un ni l'autre (pas de vérification de capacité possible, voir plan §3.3)."""
    total = 0
    has_audience = False
    for d in course.divisions:
        total += d.student_count or 0
        has_audience = True
    for g in course.groups:
        total += g.student_count or 0
        has_audience = True
    return total if has_audience else None


def _build_classroom_assignment_problem(
    db: Session, school_id: Optional[int] = None, optimize_target: str = "TEACHER"
) -> PlanningRoomTimetable:
    """
    Construit le problème CLASSROOM_ASSIGNMENT : une PlanningRoomAssignment par unité de besoin
    (quantity) de chaque CourseClassroomRequirement pointant vers un GROUPE, sur n'importe quel
    cours (parent ou enfant, §3.1 — la cascade décrémentée de la tâche #4 garantit déjà que la
    quantité stockée est correcte, aucune distinction de population nécessaire ici).

    optimize_target ("TEACHER" ou "DIVISION") : axe choisi par l'utilisateur dans le wizard
    "Attribuer les salles" pour la continuité de salle (voir room_constraints.py) — reçoit un
    poids ×10 par rapport à l'autre axe.
    """
    query = select(Course)
    if school_id is not None:
        query = query.filter(Course.school_id == school_id)
    all_courses = db.execute(query).scalars().unique().all()

    assignments = []
    fixed_bookings = []
    candidate_classrooms_by_group = {}
    all_classrooms_seen = {}

    for course in all_courses:
        effective_ts = _effective_timeslot_and_fields(db, course)
        if effective_ts is None:
            continue

        week_type_value = course.week_type.value if hasattr(course.week_type, "value") else course.week_type
        period_mask = 0  # aligné sur la valeur par défaut utilisée côté COURSE_PLACEMENT pour un cours sans période explicite ; voir note ci-dessous.
        if course.periods:
            # Reconstruit le même bitmask que _build_course_placement_problem (solver.py) —
            # dupliqué ici plutôt que partagé : les deux constructions restent indépendantes
            # (pas de fait partagé entre les deux domaines), cohérent avec la séparation des
            # deux SolverFactory.
            from backend.app.models.period import Period
            db_periods = db.execute(select(Period)).scalars().unique().all()
            period_to_bit = {p.id: (1 << i) for i, p in enumerate(db_periods)}
            period_mask = sum(period_to_bit.get(p.id, 0) for p in course.periods)

        teacher_ids = [t.id for t in course.teachers]
        division_ids = [d.id for d in course.divisions]
        teacher_preferred_ids = [t.preferred_classroom_id for t in course.teachers if t.preferred_classroom_id is not None]
        division_preferred_ids = [d.preferred_classroom_id for d in course.divisions if d.preferred_classroom_id is not None]
        effective_headcount = _effective_headcount(course)

        for req in course.classroom_requirements:
            if req.quantity <= 0:
                continue
            classroom = req.classroom
            if not classroom.children_classrooms:
                # Salle-feuille précise : occupation déjà connue, pas une PlanningRoomAssignment
                # à résoudre — devient un fait PlanningFixedRoomBooking (voir plus bas).
                continue

            if req.classroom_id not in candidate_classrooms_by_group:
                leaf_ids = leaf_classroom_ids_under(db, req.classroom_id)
                candidates = []
                for leaf_id in leaf_ids:
                    if leaf_id not in all_classrooms_seen:
                        leaf_classroom = db.get(Classroom, leaf_id)
                        all_classrooms_seen[leaf_id] = PlanningClassroom(
                            id=leaf_classroom.id, name=leaf_classroom.name, capacity=leaf_classroom.capacity
                        )
                    candidates.append(all_classrooms_seen[leaf_id])
                candidate_classrooms_by_group[req.classroom_id] = candidates

            candidate_classrooms = candidate_classrooms_by_group[req.classroom_id]

            for unit_index in range(req.quantity):
                assignments.append(PlanningRoomAssignment(
                    id=req.id * 100 + unit_index,
                    course_id=course.id,
                    day_of_week=effective_ts.day_of_week,
                    minutes_from_midnight=effective_ts.minutes_from_midnight,
                    duration_minutes=course.duration_minutes,
                    week_type=week_type_value,
                    period_mask=period_mask,
                    timeslot_id=effective_ts.id,
                    teacher_ids=teacher_ids,
                    division_ids=division_ids,
                    teacher_preferred_classroom_ids=teacher_preferred_ids,
                    division_preferred_classroom_ids=division_preferred_ids,
                    effective_headcount=effective_headcount,
                    candidate_classrooms=candidate_classrooms,
                ))

        for req in course.classroom_requirements:
            classroom = req.classroom
            if classroom.children_classrooms:
                continue  # groupe, déjà traité ci-dessus
            fixed_bookings.append(PlanningFixedRoomBooking(
                classroom_id=req.classroom_id,
                day_of_week=effective_ts.day_of_week,
                minutes_from_midnight=effective_ts.minutes_from_midnight,
                duration_minutes=course.duration_minutes,
                week_type=week_type_value,
                period_mask=period_mask,
                teacher_ids=teacher_ids,
                division_ids=division_ids,
            ))
            if req.classroom_id not in all_classrooms_seen:
                all_classrooms_seen[req.classroom_id] = PlanningClassroom(
                    id=classroom.id, name=classroom.name, capacity=classroom.capacity
                )

    db_preferences = db.execute(select(ResourcePreference)).scalars().unique().all()
    preferences_list = [
        PlanningPreference(
            id=pref.id,
            resource_type=pref.resource_type,
            resource_id=pref.resource_id,
            timeslot_id=pref.timeslot_id,
            preference_level=pref.preference_level,
            week_type=pref.week_type,
            period_ids=[],
            period_mask=0,
        ) for pref in db_preferences
    ]

    optimization_settings = [PlanningRoomOptimizationSettings(optimize_target=optimize_target)]
    assert len(optimization_settings) == 1

    return PlanningRoomTimetable(
        classrooms=list(all_classrooms_seen.values()),
        fixed_bookings=fixed_bookings,
        preferences=preferences_list,
        optimization_settings=optimization_settings,
        assignments=assignments,
        score=None,
    )


def _write_back_classroom_assignment(db, solution):
    """Écrit le résultat d'un solve CLASSROOM_ASSIGNMENT en base — mécanisme de sortie de domaine
    (Option 1, décidée en amont) : chaque PlanningRoomAssignment résolue passe par
    CourseClassroomRequirement.create()/update() (CRUDMixin normal, PAS une écriture directe) pour
    que la cascade de décrémentation (§1.5) se déclenche naturellement. Ne fait PAS le commit — à
    la charge de l'appelant.

    Toujours une scission (jamais de transformation en place) : classroom_id est immuable après
    création (voir CourseClassroomRequirement._validate_classroom_id_immutable) — une ligne de
    groupe résolue devient donc systématiquement une NOUVELLE ligne précise à quantity=1, la ligne
    d'origine étant décrémentée (ou supprimée si elle tombe à 0). `_skip_ancestor_decrement=True`
    sur la nouvelle ligne : cette unité de besoin a déjà été décomptée auprès d'un éventuel ancêtre
    au moment de la création de la ligne d'origine (voir _cascade_decrement_parent_group_line) —
    la recompter ici la compterait deux fois pour un seul besoin réel (bug confirmé, corrigé ici)."""
    for assignment in solution.assignments:
        if assignment.classroom is None:
            continue
        req_id = assignment.id // 100
        req = db.get(CourseClassroomRequirement, req_id)
        if req is None:
            continue  # ligne déjà transformée lors d'une itération précédente
        CourseClassroomRequirement.create(db, {
            "course_id": req.course_id,
            "classroom_id": assignment.classroom.id,
            "quantity": 1,
            "_skip_ancestor_decrement": True,
        })
        if req.quantity > 1:
            req.update(db, {"quantity": req.quantity - 1})
        else:
            req.delete(db)


def solve_classroom_assignment(
    db: Session,
    school_id: Optional[int] = None,
    termination_config_override=None,
    optimize_target: str = "TEACHER",
):
    """
    Résout CLASSROOM_ASSIGNMENT et écrit le résultat en base. Write-back = mécanisme de sortie de
    domaine (Option 1, décidée en amont) : chaque PlanningRoomAssignment résolue passe par
    CourseClassroomRequirement.create() (CRUDMixin normal, PAS une écriture directe) pour que la
    cascade de décrémentation (§1.5) se déclenche naturellement — le volume ici est celui des
    cours porteurs d'une exigence de groupe, pas la totalité des cours de l'établissement comme
    pour le write-back COURSE_PLACEMENT, d'où ce choix (voir plan salles §1.5, point de
    vigilance).

    NOTE D'ORCHESTRATION : cette fonction ne gère ni le sémaphore/la file (SolverState), ni le
    mode exclusif, ni le threading arrière-plan — l'orchestration de production
    (start_classroom_assignment_async, solver.py) réutilise ses briques séparément
    (_build_classroom_assignment_problem/_get_classroom_assignment_solver_factory/
    _write_back_classroom_assignment) via _run_job_phases, pas cette fonction telle quelle.
    Reste le point d'entrée le plus direct pour tester ce domaine indépendamment de
    l'orchestration (voir test_solver.py).
    """
    from timefold.solver.config import SolverConfigOverride, TerminationConfig, Duration
    from backend.app.core.config import settings

    problem = _build_classroom_assignment_problem(db, school_id, optimize_target)
    solver_factory = _get_classroom_assignment_solver_factory()

    override = termination_config_override or SolverConfigOverride(
        termination_config=TerminationConfig(
            spent_limit=Duration(seconds=settings.SOLVER_TIME_LIMIT_SECONDS),
            unimproved_spent_limit=Duration(seconds=settings.SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS),
        )
    )
    solver = solver_factory.build_solver(solver_config_override=override)
    solution = solver.solve(problem)

    _write_back_classroom_assignment(db, solution)

    return solution

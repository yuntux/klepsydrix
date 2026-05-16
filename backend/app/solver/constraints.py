from dataclasses import dataclass, field
from typing import List, Annotated
from timefold.solver.domain import (
    planning_entity,
    PlanningVariable,
    PlanningId,
    planning_solution,
    ProblemFactCollectionProperty,
    PlanningEntityCollectionProperty,
    PlanningScore,
    ValueRangeProvider,
)
from timefold.solver.score import easy_score_calculator, HardSoftScore

# Patch PlanningScore to enforce HardSoftLongScore type in Java layer
# to avoid translation type issues in JPype/Timefold
from timefold.solver.domain._annotations import ensure_init
ensure_init()
from timefold.solver._timefold_java_interop import register_python_java_type_mappings
register_python_java_type_mappings()

from ai.timefold.solver.core.api.score.buildin.hardsoftlong import HardSoftLongScore as JavaHardSoftLongScore
original_planning_score_init = PlanningScore.__init__
def patched_planning_score_init(self, *args, **kwargs):
    original_planning_score_init(self, *args, **kwargs)
    self.field_type_override = JavaHardSoftLongScore
PlanningScore.__init__ = patched_planning_score_init


# --- ENTIRES DE PLANIFICATION TIMEFOLD ---

@dataclass
class PlanningTeacher:
    id: int
    name: str


@dataclass
class PlanningClassroom:
    id: int
    name: str
    capacity: int


@dataclass
class PlanningDivision:
    id: int
    name: str


@dataclass
class PlanningTimeslot:
    id: int
    day_of_week: int
    hour: int


@planning_entity
@dataclass
class PlanningCourse:
    id: Annotated[int, PlanningId]
    subject: str
    teacher: PlanningTeacher
    division: PlanningDivision
    timeslot: Annotated[PlanningTimeslot, PlanningVariable(value_range_provider_refs=['timeslotRange'])] = None
    classroom: Annotated[PlanningClassroom, PlanningVariable(value_range_provider_refs=['classroomRange'])] = None


@planning_solution
@dataclass
class PlanningTimetable:
    teachers: Annotated[List[PlanningTeacher], ProblemFactCollectionProperty]
    classrooms: Annotated[List[PlanningClassroom], ProblemFactCollectionProperty, ValueRangeProvider(id='classroomRange')]
    divisions: Annotated[List[PlanningDivision], ProblemFactCollectionProperty]
    timeslots: Annotated[List[PlanningTimeslot], ProblemFactCollectionProperty, ValueRangeProvider(id='timeslotRange')]
    courses: Annotated[List[PlanningCourse], PlanningEntityCollectionProperty]
    score: Annotated[HardSoftScore, PlanningScore]


@easy_score_calculator
def calculate_score(solution: PlanningTimetable) -> HardSoftScore:
    hard_score = 0
    soft_score = 0

    placed_courses = [c for c in solution.courses if c.timeslot is not None and c.classroom is not None]
    unplaced_count = len(solution.courses) - len(placed_courses)
    hard_score -= unplaced_count * 10

    # 1. Contraintes Dures : Évaluation en O(N) par regroupement par créneau (timeslot)
    by_timeslot = {}
    for c in placed_courses:
        by_timeslot.setdefault(c.timeslot.id, []).append(c)

    for courses_in_slot in by_timeslot.values():
        if len(courses_in_slot) < 2:
            continue
        
        teachers = set()
        classrooms = set()
        divisions = set()
        
        for c in courses_in_slot:
            # Conflit enseignant
            if c.teacher.id in teachers:
                hard_score -= 1
            else:
                teachers.add(c.teacher.id)
                
            # Conflit salle
            if c.classroom.id in classrooms:
                hard_score -= 1
            else:
                classrooms.add(c.classroom.id)
                
            # Conflit division
            if c.division.id in divisions:
                hard_score -= 1
            else:
                divisions.add(c.division.id)

    # 2. Contraintes Souples : Évaluation optimisée en O(N) sans boucler sur tous les profs/divisions
    # A. Trous des Enseignants (FR-008)
    courses_by_teacher_day = {}
    for c in placed_courses:
        courses_by_teacher_day.setdefault((c.teacher.id, c.timeslot.day_of_week), []).append(c.timeslot.hour)

    for hours in courses_by_teacher_day.values():
        if len(hours) < 2:
            continue
        min_hour = min(hours)
        max_hour = max(hours)
        hours_set = set(hours)
        for h in range(min_hour + 1, max_hour):
            if h not in hours_set:
                soft_score -= 1

    # B. Trous des Divisions d'élèves (FR-012)
    courses_by_div_day = {}
    for c in placed_courses:
        courses_by_div_day.setdefault((c.division.id, c.timeslot.day_of_week), []).append(c.timeslot.hour)

    for hours in courses_by_div_day.values():
        if len(hours) < 2:
            continue
        min_hour = min(hours)
        max_hour = max(hours)
        hours_set = set(hours)
        for h in range(min_hour + 1, max_hour):
            if h not in hours_set:
                soft_score -= 1

    return HardSoftScore.of(hard_score, soft_score)


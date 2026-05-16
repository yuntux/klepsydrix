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
from timefold.solver.score import constraint_provider, ConstraintFactory, Joiners, Constraint, HardSoftScore

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


@constraint_provider
def define_constraints(constraint_factory: ConstraintFactory) -> list[Constraint]:
    return [
        teacher_conflict(constraint_factory),
        classroom_conflict(constraint_factory),
        division_conflict(constraint_factory),
    ]

def teacher_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot),
            Joiners.equal(lambda course: course.teacher)
        )
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Teacher conflict")
    )

def classroom_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot),
            Joiners.equal(lambda course: course.classroom)
        )
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Classroom conflict")
    )

def division_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot),
            Joiners.equal(lambda course: course.division)
        )
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Division conflict")
    )


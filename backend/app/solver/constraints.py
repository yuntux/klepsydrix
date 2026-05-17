from dataclasses import dataclass, field
from typing import List, Annotated
import typing
from timefold.solver.domain import (
    planning_entity,
    PlanningVariable,
    PlanningId,
    planning_solution,
    ProblemFactCollectionProperty,
    PlanningEntityCollectionProperty,
    PlanningScore,
    ValueRangeProvider,
    PlanningPin,
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


# --- ENTITÉS DE PLANIFICATION TIMEFOLD ---

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


@dataclass
class PlanningClassPartLink:
    class_part_a_id: int
    class_part_b_id: int


@dataclass
class PlanningPreference:
    id: int
    resource_type: str
    resource_id: int
    timeslot_id: int
    preference_level: str


@planning_entity
@dataclass
class PlanningCourse:
    id: Annotated[int, PlanningId]
    subject: str
    teacher: PlanningTeacher
    division: PlanningDivision
    timeslot: Annotated[PlanningTimeslot, PlanningVariable(value_range_provider_refs=['timeslotRange'])] = None
    classroom: Annotated[PlanningClassroom, PlanningVariable(value_range_provider_refs=['classroomRange'])] = None
    is_pinned: Annotated[bool, PlanningPin] = False
    original_timeslot_id: typing.Optional[int] = None
    
    # Alternance et parties de classe (US2)
    week_type: str = "T"
    class_part_ids: List[int] = field(default_factory=list)


@planning_solution
@dataclass
class PlanningTimetable:
    teachers: Annotated[List[PlanningTeacher], ProblemFactCollectionProperty]
    classrooms: Annotated[List[PlanningClassroom], ProblemFactCollectionProperty, ValueRangeProvider(id='classroomRange')]
    divisions: Annotated[List[PlanningDivision], ProblemFactCollectionProperty]
    timeslots: Annotated[List[PlanningTimeslot], ProblemFactCollectionProperty, ValueRangeProvider(id='timeslotRange')]
    courses: Annotated[List[PlanningCourse], PlanningEntityCollectionProperty]
    class_part_links: Annotated[List[PlanningClassPartLink], ProblemFactCollectionProperty] = field(default_factory=list)
    preferences: Annotated[List[PlanningPreference], ProblemFactCollectionProperty] = field(default_factory=list)
    score: Annotated[HardSoftScore, PlanningScore] = None


# --- RÈGLES DE CONTRAINTES ---

def weeks_overlap(w1: str, w2: str) -> bool:
    if w1 == "T" or w2 == "T":
        return True
    return w1 == w2


@constraint_provider
def define_constraints(constraint_factory: ConstraintFactory) -> list[Constraint]:
    return [
        teacher_conflict(constraint_factory),
        classroom_conflict(constraint_factory),
        division_conflict(constraint_factory),
        group_link_conflict(constraint_factory),
        stability_penalty(constraint_factory),
        teacher_room_stability(constraint_factory),
        student_group_subject_variety(constraint_factory),
        teacher_time_efficiency(constraint_factory),
        division_time_efficiency(constraint_factory),
        resource_preference_hard(constraint_factory),
        resource_preference_soft_penalty(constraint_factory),
        resource_preference_soft_reward(constraint_factory),
    ]

def teacher_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot),
            Joiners.equal(lambda course: course.teacher)
        )
        .filter(lambda course1, course2: weeks_overlap(course1.week_type, course2.week_type))
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
        .filter(lambda course1, course2: weeks_overlap(course1.week_type, course2.week_type))
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
        .filter(lambda course1, course2: weeks_overlap(course1.week_type, course2.week_type))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Division conflict")
    )

def group_link_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningClassPartLink)
        .join(
            PlanningCourse,
            Joiners.filtering(lambda link, course: link.class_part_a_id in course.class_part_ids or link.class_part_b_id in course.class_part_ids)
        )
        .join(
            PlanningCourse,
            Joiners.equal(lambda link, course1: course1.timeslot, lambda course2: course2.timeslot),
            Joiners.filtering(lambda link, course1, course2: course1.id < course2.id and (link.class_part_a_id in course2.class_part_ids or link.class_part_b_id in course2.class_part_ids))
        )
        .filter(lambda link, course1, course2: weeks_overlap(course1.week_type, course2.week_type))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Group link conflict")
    )

def stability_penalty(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.original_timeslot_id is not None and course.timeslot is not None and course.original_timeslot_id != course.timeslot.id)
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Minimize timetable disruption")
    )

def teacher_room_stability(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.teacher)
        )
        .filter(lambda course1, course2: course1.classroom is not None and course2.classroom is not None and course1.classroom.id != course2.classroom.id)
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Teacher room stability")
    )

def student_group_subject_variety(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.subject),
            Joiners.equal(lambda course: course.division),
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda course1, course2: course1.timeslot is not None and course2.timeslot is not None and abs(course1.timeslot.hour - course2.timeslot.hour) == 1)
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Student group subject variety")
    )

def teacher_time_efficiency(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.teacher),
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda course1, course2: course1.timeslot is not None and course2.timeslot is not None and abs(course1.timeslot.hour - course2.timeslot.hour) == 1)
        .reward(HardSoftScore.ONE_SOFT)
        .as_constraint("Teacher time efficiency")
    )

def division_time_efficiency(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.division),
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda course1, course2: course1.timeslot is not None and course2.timeslot is not None and abs(course1.timeslot.hour - course2.timeslot.hour) == 1)
        .reward(HardSoftScore.ONE_SOFT)
        .as_constraint("Division time efficiency")
    )


def resource_preference_hard(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None)
        .join(
            PlanningPreference,
            Joiners.equal(lambda course: course.timeslot.id, lambda pref: pref.timeslot_id)
        )
        .filter(lambda course, pref: pref.preference_level == "Unsuited" and (
            (pref.resource_type == "Teacher" and course.teacher is not None and pref.resource_id == course.teacher.id) or
            (pref.resource_type == "Classroom" and course.classroom is not None and pref.resource_id == course.classroom.id) or
            (pref.resource_type == "Division" and course.division is not None and pref.resource_id == course.division.id)
        ))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Resource unavailability (strict)")
    )


def resource_preference_soft_penalty(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None)
        .join(
            PlanningPreference,
            Joiners.equal(lambda course: course.timeslot.id, lambda pref: pref.timeslot_id)
        )
        .filter(lambda course, pref: pref.preference_level == "Undesirable" and (
            (pref.resource_type == "Teacher" and course.teacher is not None and pref.resource_id == course.teacher.id) or
            (pref.resource_type == "Classroom" and course.classroom is not None and pref.resource_id == course.classroom.id) or
            (pref.resource_type == "Division" and course.division is not None and pref.resource_id == course.division.id)
        ))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Resource preference undesirable")
    )


def resource_preference_soft_reward(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None)
        .join(
            PlanningPreference,
            Joiners.equal(lambda course: course.timeslot.id, lambda pref: pref.timeslot_id)
        )
        .filter(lambda course, pref: pref.preference_level == "Preferred" and (
            (pref.resource_type == "Teacher" and course.teacher is not None and pref.resource_id == course.teacher.id) or
            (pref.resource_type == "Classroom" and course.classroom is not None and pref.resource_id == course.classroom.id) or
            (pref.resource_type == "Division" and course.division is not None and pref.resource_id == course.division.id)
        ))
        .reward(HardSoftScore.ONE_SOFT)
        .as_constraint("Resource preference preferred")
    )


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
from timefold.solver.score import constraint_provider, ConstraintFactory, Joiners, Constraint, HardSoftScore, ConstraintCollectors


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


@dataclass
class PlanningResourceConstraint:
    id: int
    resource_type: str
    resource_id: typing.Optional[int]
    
    # Subject constraints
    target_subject_b_id: typing.Optional[int] = None
    incompatible_same_half_day: bool = False
    incompatible_same_day: bool = False
    incompatible_two_consecutive_days: bool = False
    min_free_half_days_between: typing.Optional[int] = None
    prevent_consecutive_a_then_b: bool = False
    prevent_consecutive_b_then_a: bool = False
    max_hours_per_day: typing.Optional[float] = None
    max_hours_per_half_day: typing.Optional[float] = None
    weekly_order_a_before_b: bool = False
    weekly_order_b_before_a: bool = False
    group_course_order: str = "NONE"

    # Teacher / Division constraints
    max_hours_per_am: typing.Optional[float] = None
    max_hours_per_pm: typing.Optional[float] = None
    max_presence_days_per_week: typing.Optional[int] = None
    max_presence_hours_per_day: typing.Optional[float] = None
    late_start_days_per_week: typing.Optional[int] = None
    late_start_time: typing.Optional[str] = None
    early_end_days_per_week: typing.Optional[int] = None
    early_end_time: typing.Optional[str] = None
    min_free_days_per_week: typing.Optional[int] = None
    min_free_half_days_per_week: typing.Optional[int] = None
    max_worked_am_per_week: typing.Optional[int] = None
    max_worked_pm_per_week: typing.Optional[int] = None
    only_one_half_day_per_day: bool = False
    max_gap_hours_per_week: int = 2


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
    resource_constraints: Annotated[List[PlanningResourceConstraint], ProblemFactCollectionProperty] = field(default_factory=list)
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
        teacher_max_hours_per_day(constraint_factory),
        teacher_max_hours_per_am(constraint_factory),
        teacher_max_hours_per_pm(constraint_factory),
        teacher_only_one_half_day_per_day(constraint_factory),
        teacher_late_start_limit(constraint_factory),
        teacher_early_end_limit(constraint_factory),
        teacher_max_presence_days(constraint_factory),
        teacher_min_free_days(constraint_factory),
        teacher_max_worked_am(constraint_factory),
        teacher_max_worked_pm(constraint_factory),
        division_max_hours_per_day(constraint_factory),
        division_max_hours_per_am(constraint_factory),
        division_max_hours_per_pm(constraint_factory),
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
        .penalize(HardSoftScore.of_soft(10))
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
        .reward(HardSoftScore.of_soft(10))
        .as_constraint("Resource preference preferred")
    )


def teacher_max_hours_per_day(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.teacher is not None)
        .group_by(
            lambda course: course.teacher,
            lambda course: course.timeslot.day_of_week,
            ConstraintCollectors.count()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher, day, count: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher, day, count: teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher, day, count, rc: rc.max_hours_per_day is not None and count > rc.max_hours_per_day)
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda teacher, day, count, rc: int((count - rc.max_hours_per_day) * 10)
        )
        .as_constraint("Teacher max hours per day")
    )


def teacher_max_hours_per_am(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.teacher is not None and course.timeslot.hour < 12)
        .group_by(
            lambda course: course.teacher,
            lambda course: course.timeslot.day_of_week,
            ConstraintCollectors.count()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher, day, count: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher, day, count: teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher, day, count, rc: rc.max_hours_per_am is not None and count > rc.max_hours_per_am)
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda teacher, day, count, rc: int((count - rc.max_hours_per_am) * 10)
        )
        .as_constraint("Teacher max hours per morning")
    )


def teacher_max_hours_per_pm(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.teacher is not None and course.timeslot.hour >= 12)
        .group_by(
            lambda course: course.teacher,
            lambda course: course.timeslot.day_of_week,
            ConstraintCollectors.count()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher, day, count: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher, day, count: teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher, day, count, rc: rc.max_hours_per_pm is not None and count > rc.max_hours_per_pm)
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda teacher, day, count, rc: int((count - rc.max_hours_per_pm) * 10)
        )
        .as_constraint("Teacher max hours per afternoon")
    )


def teacher_only_one_half_day_per_day(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.teacher),
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda c1, c2: c1.timeslot is not None and c2.timeslot is not None and (
            (c1.timeslot.hour < 12 and c2.timeslot.hour >= 12) or 
            (c1.timeslot.hour >= 12 and c2.timeslot.hour < 12)
        ))
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda c1, c2: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda c1, c2: c1.teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda c1, c2, rc: rc.only_one_half_day_per_day)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Teacher only one half day per day")
    )


def teacher_late_start_limit(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.teacher is not None)
        .group_by(
            lambda course: course.teacher,
            ConstraintCollectors.to_set(lambda course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher, timeslots_set: teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher, timeslots_set, rc: rc.late_start_time is not None and rc.late_start_days_per_week is not None)
        .filter(lambda teacher, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.hour < int(rc.late_start_time.split(':')[0])}) > (5 - rc.late_start_days_per_week))
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda teacher, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.hour < int(rc.late_start_time.split(':')[0])}) - (5 - rc.late_start_days_per_week)) * 10
        )
        .as_constraint("Teacher late start limit")
    )


def teacher_early_end_limit(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.teacher is not None)
        .group_by(
            lambda course: course.teacher,
            ConstraintCollectors.to_set(lambda course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher, timeslots_set: teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher, timeslots_set, rc: rc.early_end_time is not None and rc.early_end_days_per_week is not None)
        .filter(lambda teacher, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.hour >= float(rc.early_end_time.split(':')[0]) + (0.5 if rc.early_end_time.split(':')[1] == '30' else 0.0)}) > (5 - rc.early_end_days_per_week))
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda teacher, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.hour >= float(rc.early_end_time.split(':')[0]) + (0.5 if rc.early_end_time.split(':')[1] == '30' else 0.0)}) - (5 - rc.early_end_days_per_week)) * 10
        )
        .as_constraint("Teacher early end limit")
    )


def teacher_max_presence_days(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.teacher is not None)
        .group_by(
            lambda course: course.teacher,
            ConstraintCollectors.to_set(lambda course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher, timeslots_set: teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher, timeslots_set, rc: rc.max_presence_days_per_week is not None)
        .filter(lambda teacher, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set}) > rc.max_presence_days_per_week)
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda teacher, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set}) - rc.max_presence_days_per_week) * 10
        )
        .as_constraint("Teacher max presence days per week")
    )


def teacher_min_free_days(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.teacher is not None)
        .group_by(
            lambda course: course.teacher,
            ConstraintCollectors.to_set(lambda course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher, timeslots_set: teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher, timeslots_set, rc: rc.min_free_days_per_week is not None)
        .filter(lambda teacher, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set}) > (5 - rc.min_free_days_per_week))
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda teacher, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set}) - (5 - rc.min_free_days_per_week)) * 10
        )
        .as_constraint("Teacher min free days per week")
    )


def teacher_max_worked_am(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.teacher is not None)
        .group_by(
            lambda course: course.teacher,
            ConstraintCollectors.to_set(lambda course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher, timeslots_set: teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher, timeslots_set, rc: rc.max_worked_am_per_week is not None)
        .filter(lambda teacher, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.hour < 12}) > rc.max_worked_am_per_week)
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda teacher, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.hour < 12}) - rc.max_worked_am_per_week) * 10
        )
        .as_constraint("Teacher max worked mornings per week")
    )


def teacher_max_worked_pm(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.teacher is not None)
        .group_by(
            lambda course: course.teacher,
            ConstraintCollectors.to_set(lambda course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher, timeslots_set: teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher, timeslots_set, rc: rc.max_worked_pm_per_week is not None)
        .filter(lambda teacher, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.hour >= 12}) > rc.max_worked_pm_per_week)
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda teacher, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.hour >= 12}) - rc.max_worked_pm_per_week) * 10
        )
        .as_constraint("Teacher max worked afternoons per week")
    )


def division_max_hours_per_day(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.division is not None)
        .group_by(
            lambda course: course.division,
            lambda course: course.timeslot.day_of_week,
            ConstraintCollectors.count()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda division, day, count: "Division", lambda rc: rc.resource_type),
            Joiners.equal(lambda division, day, count: division.id, lambda rc: rc.resource_id)
        )
        .filter(lambda division, day, count, rc: rc.max_hours_per_day is not None and count > rc.max_hours_per_day)
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda division, day, count, rc: int((count - rc.max_hours_per_day) * 10)
        )
        .as_constraint("Division max hours per day")
    )


def division_max_hours_per_am(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.division is not None and course.timeslot.hour < 12)
        .group_by(
            lambda course: course.division,
            lambda course: course.timeslot.day_of_week,
            ConstraintCollectors.count()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda division, day, count: "Division", lambda rc: rc.resource_type),
            Joiners.equal(lambda division, day, count: division.id, lambda rc: rc.resource_id)
        )
        .filter(lambda division, day, count, rc: rc.max_hours_per_am is not None and count > rc.max_hours_per_am)
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda division, day, count, rc: int((count - rc.max_hours_per_am) * 10)
        )
        .as_constraint("Division max hours per morning")
    )


def division_max_hours_per_pm(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.division is not None and course.timeslot.hour >= 12)
        .group_by(
            lambda course: course.division,
            lambda course: course.timeslot.day_of_week,
            ConstraintCollectors.count()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda division, day, count: "Division", lambda rc: rc.resource_type),
            Joiners.equal(lambda division, day, count: division.id, lambda rc: rc.resource_id)
        )
        .filter(lambda division, day, count, rc: rc.max_hours_per_pm is not None and count > rc.max_hours_per_pm)
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda division, day, count, rc: int((count - rc.max_hours_per_pm) * 10)
        )
        .as_constraint("Division max hours per afternoon")
    )



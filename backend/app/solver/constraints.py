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
class PlanningNonTeachingStaff:
    id: int
    first_name: str
    last_name: str


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
    hour: float
    absolute_end_of_day: float


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
    week_type: str = "W"
    period_ids: List[int] = field(default_factory=list)


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


def hierarchy_overlap(c1: 'PlanningCourse', c2: 'PlanningCourse') -> bool:
    if c1.parent_id is not None and c1.parent_id == c2.id:
        return False
    if c2.parent_id is not None and c2.parent_id == c1.id:
        return False
    if c1.parent_id is not None and c2.parent_id is not None and c1.parent_id == c2.parent_id:
        return False
    return True

@planning_entity
@dataclass
class PlanningCourse:
    id: Annotated[int, PlanningId]
    step: float
    subject_id: typing.Optional[int] = None
    teachers: List[PlanningTeacher] = field(default_factory=list)
    non_teaching_staffs: List[PlanningNonTeachingStaff] = field(default_factory=list)
    divisions: List[PlanningDivision] = field(default_factory=list)
    timeslot: Annotated[typing.Optional[PlanningTimeslot], PlanningVariable(value_range_provider_refs=['timeslotRange'], allows_unassigned=True)] = None
    classroom: Annotated[typing.Optional[PlanningClassroom], PlanningVariable(value_range_provider_refs=['classroomRange'])] = None
    is_pinned: Annotated[bool, PlanningPin] = False
    original_timeslot_id: typing.Optional[int] = None
    original_classroom_id: typing.Optional[int] = None
    parent_id: typing.Optional[int] = None
    
    # Alternance et parties de classe (US2)
    week_type: str = "W"
    class_part_ids: List[int] = field(default_factory=list)
    period_ids: List[int] = field(default_factory=list)

@planning_solution
@dataclass
class PlanningTimetable:
    teachers: Annotated[List[PlanningTeacher], ProblemFactCollectionProperty]
    non_teaching_staffs: Annotated[List[PlanningNonTeachingStaff], ProblemFactCollectionProperty]
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
    if w1 == "W" or w2 == "W":
        return True
    return w1 == w2


def time_to_float(time_str: str) -> float:
    parts = time_str.split(':')
    return float(parts[0]) + float(parts[1]) / 60.0


def periods_overlap(periods_a: List[int], periods_b: List[int]) -> bool:
    if not periods_a or not periods_b:
        return True
    return any(p in periods_b for p in periods_a)


@constraint_provider
def define_constraints(constraint_factory: ConstraintFactory) -> list[Constraint]:
    return [
        penalize_unassigned_course(constraint_factory),
        teacher_conflict(constraint_factory),
        non_teaching_staff_conflict(constraint_factory),
        classroom_conflict(constraint_factory),
        classroom_immobility(constraint_factory),
        division_conflict(constraint_factory),
        group_link_conflict(constraint_factory),
        course_day_overflow(constraint_factory),
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

def _courses_overlap_in_time(c1, c2):
    if c1.timeslot is None or c2.timeslot is None:
        return False
    start1 = round(c1.timeslot.hour * 60)
    end1 = start1 + round(c1.step * 60)
    start2 = round(c2.timeslot.hour * 60)
    end2 = start2 + round(c2.step * 60)
    return start1 < end2 and start2 < end1

def _check_teacher_overlap(c1, c2):
    for t1 in c1.teachers:
        for t2 in c2.teachers:
            if t1.id == t2.id:
                return True
    return False

# ==========================================
# 0. OVERCONSTRAINED PLANNING
# ==========================================

def penalize_unassigned_course(constraint_factory: ConstraintFactory) -> Constraint:
    """
    Overconstrained Planning : on autorise Timefold à ne pas placer un cours (timeslot=None)
    si le placer créerait un conflit dur (Hard Conflict).
    Pour éviter que Timefold ne place rien du tout, on ajoute une très forte pénalité Soft.
    Ainsi, l'IA cherchera toujours à le placer, sauf si c'est physiquement impossible.
    NOTE: On DOIT utiliser `for_each_including_unassigned` car `for_each` ignore les variables None.
    """
    return (
        constraint_factory.for_each_including_unassigned(PlanningCourse)
        .filter(lambda c: getattr(c, 'timeslot', None) is None)
        .penalize(HardSoftScore.ONE_SOFT, lambda c: 1_000_000)
        .as_constraint("Pénaliser les cours non assignés (Overconstrained Planning)")
    )


# ==========================================
# 1. CONTRAINTES DURES (HardScore)
# ==========================================

def course_day_overflow(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None)
        .filter(lambda course: (course.timeslot.hour + course.step) > course.timeslot.absolute_end_of_day)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Course day overflow")
    )

def teacher_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda course1, course2: weeks_overlap(course1.week_type, course2.week_type))
        .filter(lambda course1, course2: periods_overlap(course1.period_ids, course2.period_ids))
        .filter(lambda course1, course2: hierarchy_overlap(course1, course2))
        .filter(_courses_overlap_in_time)
        .filter(_check_teacher_overlap)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Teacher conflict")
    )

def _check_non_teaching_staff_overlap(c1, c2):
    for s1 in c1.non_teaching_staffs:
        for s2 in c2.non_teaching_staffs:
            if s1.id == s2.id:
                return True
    return False

def non_teaching_staff_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda course1, course2: weeks_overlap(course1.week_type, course2.week_type))
        .filter(lambda course1, course2: periods_overlap(course1.period_ids, course2.period_ids))
        .filter(lambda course1, course2: hierarchy_overlap(course1, course2))
        .filter(_courses_overlap_in_time)
        .filter(_check_non_teaching_staff_overlap)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Non-teaching staff conflict")
    )

def classroom_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1),
            Joiners.equal(lambda course: course.classroom.id if course.classroom is not None else -1)
        )
        .filter(lambda course1, course2: weeks_overlap(course1.week_type, course2.week_type))
        .filter(lambda course1, course2: periods_overlap(course1.period_ids, course2.period_ids))
        .filter(lambda course1, course2: hierarchy_overlap(course1, course2))
        .filter(_courses_overlap_in_time)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Classroom conflict")
    )

def classroom_immobility(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.original_classroom_id is not None)
        .filter(lambda course: course.classroom is None or course.classroom.id != course.original_classroom_id)
        .penalize(HardSoftScore.of_hard(100))
        .as_constraint("Classroom immobility")
    )

def _check_division_overlap(c1, c2):
    for d1 in c1.divisions:
        for d2 in c2.divisions:
            if d1.id == d2.id:
                return True
    return False

def division_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda course1, course2: weeks_overlap(course1.week_type, course2.week_type))
        .filter(lambda course1, course2: periods_overlap(course1.period_ids, course2.period_ids))
        .filter(lambda course1, course2: hierarchy_overlap(course1, course2))
        .filter(_courses_overlap_in_time)
        .filter(_check_division_overlap)
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
            Joiners.equal(lambda link, course1: course1.timeslot.id if course1.timeslot is not None else -1, lambda course2: course2.timeslot.id if course2.timeslot is not None else -2),
            Joiners.filtering(lambda link, course1, course2: course1.id < course2.id and (link.class_part_a_id in course2.class_part_ids or link.class_part_b_id in course2.class_part_ids))
        )
        .filter(lambda link, course1, course2: weeks_overlap(course1.week_type, course2.week_type))
        .filter(lambda link, course1, course2: periods_overlap(course1.period_ids, course2.period_ids))
        .filter(lambda link, course1, course2: hierarchy_overlap(course1, course2))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Group link conflict")
    )

def stability_penalty(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.original_timeslot_id is not None and course.timeslot is not None and course.original_timeslot_id != (course.timeslot.id if course.timeslot is not None else -1))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Minimize timetable disruption")
    )

def teacher_room_stability(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(PlanningCourse)
        .filter(lambda course1, course2: course1.classroom is not None and course2.classroom is not None and course1.classroom.id != course2.classroom.id)
        .filter(_courses_share_teacher)
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Teacher room stability")
    )

def student_group_subject_variety(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.subject_id),
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda course1, course2: course1.timeslot is not None and course2.timeslot is not None and abs(abs(course1.timeslot.hour - course2.timeslot.hour) - course1.step) < 0.001)
        .filter(_courses_share_division)
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Student group subject variety")
    )

def teacher_time_efficiency(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda course1, course2: course1.timeslot is not None and course2.timeslot is not None and abs(abs(course1.timeslot.hour - course2.timeslot.hour) - course1.step) < 0.001)
        .filter(_courses_share_teacher)
        .reward(HardSoftScore.ONE_SOFT)
        .as_constraint("Teacher time efficiency")
    )

def division_time_efficiency(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda course1, course2: course1.timeslot is not None and course2.timeslot is not None and abs(abs(course1.timeslot.hour - course2.timeslot.hour) - course1.step) < 0.001)
        .filter(_courses_share_division)
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
        .filter(lambda course, pref: pref.preference_level == "Unsuited" and weeks_overlap(course.week_type, pref.week_type) and periods_overlap(course.period_ids, pref.period_ids))
        .filter(lambda course, pref: _is_preference_violated(pref, course))
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
        .filter(lambda course, pref: pref.preference_level == "Undesirable" and weeks_overlap(course.week_type, pref.week_type) and periods_overlap(course.period_ids, pref.period_ids))
        .filter(lambda course, pref: _is_preference_violated(pref, course))
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
        .filter(lambda course, pref: pref.preference_level == "Preferred" and weeks_overlap(course.week_type, pref.week_type) and periods_overlap(course.period_ids, pref.period_ids))
        .filter(lambda course, pref: _is_preference_violated(pref, course))
        .reward(HardSoftScore.of_soft(10))
        .as_constraint("Resource preference preferred")
    )



def _courses_share_teacher(c1, c2):
    for t1 in c1.teachers:
        for t2 in c2.teachers:
            if t1.id == t2.id:
                return True
    return False

def _courses_share_division(c1, c2):
    for d1 in c1.divisions:
        for d2 in c2.divisions:
            if d1.id == d2.id:
                return True
    return False

def _is_preference_violated(pref, course):
    if pref.resource_type == "Teacher":
        for t in course.teachers:
            if t.id == pref.resource_id:
                return True
        return False
    elif pref.resource_type == "Classroom":
        return course.classroom is not None and course.classroom.id == pref.resource_id
    elif pref.resource_type == "Division":
        for d in course.divisions:
            if d.id == pref.resource_id:
                return True
        return False
    return False


def _course_has_teacher(teacher, course):
    for t in course.teachers:
        if t.id == teacher.id:
            return True
    return False

def _course_has_division(division, course):
    for d in course.divisions:
        if d.id == division.id:
            return True
    return False

def teacher_max_hours_per_day(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None)
        .group_by(
            lambda teacher, course: teacher.id,
            lambda teacher, course: course.timeslot.day_of_week,
            ConstraintCollectors.count_bi()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher_id, day, count: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher_id, day, count: teacher_id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher_id, day, count, rc: rc.max_hours_per_day is not None and count > rc.max_hours_per_day)
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, day, count, rc: int((count - rc.max_hours_per_day) * 10))
        .as_constraint("Teacher max hours per day")
    )

def teacher_max_hours_per_am(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None and course.timeslot.hour < 12)
        .group_by(
            lambda teacher, course: teacher.id,
            lambda teacher, course: course.timeslot.day_of_week,
            ConstraintCollectors.count_bi()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher_id, day, count: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher_id, day, count: teacher_id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher_id, day, count, rc: rc.max_hours_per_am is not None and count > rc.max_hours_per_am)
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, day, count, rc: int((count - rc.max_hours_per_am) * 10))
        .as_constraint("Teacher max hours per morning")
    )

def teacher_max_hours_per_pm(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None and course.timeslot.hour >= 12)
        .group_by(
            lambda teacher, course: teacher.id,
            lambda teacher, course: course.timeslot.day_of_week,
            ConstraintCollectors.count_bi()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher_id, day, count: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher_id, day, count: teacher_id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher_id, day, count, rc: rc.max_hours_per_pm is not None and count > rc.max_hours_per_pm)
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, day, count, rc: int((count - rc.max_hours_per_pm) * 10))
        .as_constraint("Teacher max hours per afternoon")
    )

def teacher_only_one_half_day_per_day(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None)
        .group_by(
            lambda teacher, course: teacher.id,
            lambda teacher, course: course.timeslot.day_of_week,
            ConstraintCollectors.to_set(lambda teacher, course: course.timeslot)
        )
        .filter(lambda teacher_id, day, timeslots_set: any(ts.hour < 12 for ts in timeslots_set) and any(ts.hour >= 12 for ts in timeslots_set))
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher_id, day, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher_id, day, timeslots_set: teacher_id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher_id, day, timeslots_set, rc: rc.only_one_half_day_per_day)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Teacher only one half day per day")
    )

def teacher_late_start_limit(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None)
        .group_by(
            lambda teacher, course: teacher.id,
            ConstraintCollectors.to_set(lambda teacher, course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher_id, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher_id, timeslots_set: teacher_id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher_id, timeslots_set, rc: rc.late_start_time is not None and rc.late_start_days_per_week is not None)
        .filter(lambda teacher_id, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.hour < time_to_float(rc.late_start_time)}) > (5 - rc.late_start_days_per_week))
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.hour < time_to_float(rc.late_start_time)}) - (5 - rc.late_start_days_per_week)) * 10)
        .as_constraint("Teacher late start limit")
    )

def teacher_early_end_limit(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None)
        .group_by(
            lambda teacher, course: teacher.id,
            ConstraintCollectors.to_set(lambda teacher, course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher_id, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher_id, timeslots_set: teacher_id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher_id, timeslots_set, rc: rc.early_end_time is not None and rc.early_end_days_per_week is not None)
        .filter(lambda teacher_id, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.hour >= time_to_float(rc.early_end_time)}) > (5 - rc.early_end_days_per_week))
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.hour >= time_to_float(rc.early_end_time)}) - (5 - rc.early_end_days_per_week)) * 10)
        .as_constraint("Teacher early end limit")
    )

def teacher_max_presence_days(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None)
        .group_by(
            lambda teacher, course: teacher.id,
            ConstraintCollectors.to_set(lambda teacher, course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher_id, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher_id, timeslots_set: teacher_id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher_id, timeslots_set, rc: rc.max_presence_days_per_week is not None)
        .filter(lambda teacher_id, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set}) > rc.max_presence_days_per_week)
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set}) - rc.max_presence_days_per_week) * 10)
        .as_constraint("Teacher max presence days per week")
    )

def teacher_min_free_days(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None)
        .group_by(
            lambda teacher, course: teacher.id,
            ConstraintCollectors.to_set(lambda teacher, course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher_id, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher_id, timeslots_set: teacher_id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher_id, timeslots_set, rc: rc.min_free_days_per_week is not None)
        .filter(lambda teacher_id, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set}) > (5 - rc.min_free_days_per_week))
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set}) - (5 - rc.min_free_days_per_week)) * 10)
        .as_constraint("Teacher min free days per week")
    )

def teacher_max_worked_am(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None)
        .group_by(
            lambda teacher, course: teacher.id,
            ConstraintCollectors.to_set(lambda teacher, course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher_id, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher_id, timeslots_set: teacher_id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher_id, timeslots_set, rc: rc.max_worked_am_per_week is not None)
        .filter(lambda teacher_id, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.hour < 12}) > rc.max_worked_am_per_week)
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.hour < 12}) - rc.max_worked_am_per_week) * 10)
        .as_constraint("Teacher max worked mornings per week")
    )

def teacher_max_worked_pm(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None)
        .group_by(
            lambda teacher, course: teacher.id,
            ConstraintCollectors.to_set(lambda teacher, course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher_id, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher_id, timeslots_set: teacher_id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher_id, timeslots_set, rc: rc.max_worked_pm_per_week is not None)
        .filter(lambda teacher_id, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.hour >= 12}) > rc.max_worked_pm_per_week)
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.hour >= 12}) - rc.max_worked_pm_per_week) * 10)
        .as_constraint("Teacher max worked afternoons per week")
    )

def division_max_hours_per_day(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningDivision)
        .join(PlanningCourse, Joiners.filtering(_course_has_division))
        .filter(lambda division, course: course.timeslot is not None)
        .group_by(
            lambda division, course: division.id,
            lambda division, course: course.timeslot.day_of_week,
            ConstraintCollectors.count_bi()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda division_id, day, count: "Division", lambda rc: rc.resource_type),
            Joiners.equal(lambda division_id, day, count: division_id, lambda rc: rc.resource_id)
        )
        .filter(lambda division_id, day, count, rc: rc.max_hours_per_day is not None and count > rc.max_hours_per_day)
        .penalize(HardSoftScore.ONE_HARD, lambda division_id, day, count, rc: int((count - rc.max_hours_per_day) * 10))
        .as_constraint("Division max hours per day")
    )

def division_max_hours_per_am(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningDivision)
        .join(PlanningCourse, Joiners.filtering(_course_has_division))
        .filter(lambda division, course: course.timeslot is not None and course.timeslot.hour < 12)
        .group_by(
            lambda division, course: division.id,
            lambda division, course: course.timeslot.day_of_week,
            ConstraintCollectors.count_bi()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda division_id, day, count: "Division", lambda rc: rc.resource_type),
            Joiners.equal(lambda division_id, day, count: division_id, lambda rc: rc.resource_id)
        )
        .filter(lambda division_id, day, count, rc: rc.max_hours_per_am is not None and count > rc.max_hours_per_am)
        .penalize(HardSoftScore.ONE_HARD, lambda division_id, day, count, rc: int((count - rc.max_hours_per_am) * 10))
        .as_constraint("Division max hours per morning")
    )

def division_max_hours_per_pm(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningDivision)
        .join(PlanningCourse, Joiners.filtering(_course_has_division))
        .filter(lambda division, course: course.timeslot is not None and course.timeslot.hour >= 12)
        .group_by(
            lambda division, course: division.id,
            lambda division, course: course.timeslot.day_of_week,
            ConstraintCollectors.count_bi()
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda division_id, day, count: "Division", lambda rc: rc.resource_type),
            Joiners.equal(lambda division_id, day, count: division_id, lambda rc: rc.resource_id)
        )
        .filter(lambda division_id, day, count, rc: rc.max_hours_per_pm is not None and count > rc.max_hours_per_pm)
        .penalize(HardSoftScore.ONE_HARD, lambda division_id, day, count, rc: int((count - rc.max_hours_per_pm) * 10))
        .as_constraint("Division max hours per afternoon")
    )





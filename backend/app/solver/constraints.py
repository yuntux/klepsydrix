from dataclasses import dataclass, field
from typing import List, Annotated
import typing
from backend.app.models.timeslot import Timeslot
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
    max_pedagogic_weight_per_day: typing.Optional[float] = None
    max_pedagogic_weight_per_morning: typing.Optional[float] = None
    max_pedagogic_weight_per_afternoon: typing.Optional[float] = None


@dataclass
class PlanningTimeslot:
    id: int
    day_of_week: int
    minutes_from_midnight: int
    absolute_end_of_day: int
    noon_boundary_minutes: int


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
    period_mask: int = 0


@dataclass
class PlanningCourseToCourseConstraint:
    id: int
    type: str  # 'FORCE_SAME_SCOPE', 'FORBID_SAME_SCOPE', 'ORDER', 'FORBID_CONSECUTIVE'
    scope: str = "SLOT"  # 'SLOT', 'DAY', 'HALF_DAY', 'QUINZAINE', 'CUSTOM_HALF_DAYS'
    custom_half_days: typing.Optional[int] = None
    course_ids: List[int] = field(default_factory=list)
    is_optional: bool = True
    label: typing.Optional[str] = None


@dataclass
class PlanningResourceConstraint:
    id: int
    resource_type: str
    resource_id: typing.Optional[int]
    is_optional: bool = True
    target_subject_a_id: typing.Optional[int] = None
    
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
    weekly_order: str = "NONE"
    group_course_order: str = "NONE"
    max_separation: str = "NONE"
    division_ids: typing.List[int] = field(default_factory=list)  # Périmètre de classes (vide = toutes)

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
    duration_minutes: int
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
    pedagogic_weight_total: float = 0.0
    
    # Alternance et parties de classe (US2)
    week_type: str = "W"
    class_part_ids: List[int] = field(default_factory=list)
    period_ids: List[int] = field(default_factory=list)
    period_mask: int = 0
    all_division_ids: List[int] = field(default_factory=list)
    is_full_class: bool = False

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
    course_to_course_constraints: Annotated[List[PlanningCourseToCourseConstraint], ProblemFactCollectionProperty] = field(default_factory=list)
    score: Annotated[HardSoftScore, PlanningScore] = None


# --- RÈGLES DE CONTRAINTES ---

def weeks_overlap(w1: str, w2: str) -> bool:
    if w1 == "W" or w2 == "W":
        return True
    return w1 == w2


def time_to_minutes(time_str: str) -> int:
    parts = time_str.split(':')
    return int(parts[0]) * 60 + int(parts[1])


def periods_overlap(mask_a: int, mask_b: int) -> bool:
    if mask_a == 0 or mask_b == 0:
        return True
    return (mask_a & mask_b) != 0


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
        division_max_pedagogic_weight_per_day(constraint_factory),
        division_max_pedagogic_weight_per_am(constraint_factory),
        division_max_pedagogic_weight_per_pm(constraint_factory),
        course_to_course_force_same_scope_mandatory(constraint_factory),
        course_to_course_force_same_scope_optional(constraint_factory),
        course_to_course_forbid_same_scope_mandatory(constraint_factory),
        course_to_course_forbid_same_scope_optional(constraint_factory),
        course_to_course_order_mandatory(constraint_factory),
        course_to_course_order_optional(constraint_factory),
        course_to_course_forbid_consecutive_mandatory(constraint_factory),
        course_to_course_forbid_consecutive_optional(constraint_factory),
        subject_default_incompatible_same_day(constraint_factory),
        subject_incompatible_same_half_day_mandatory(constraint_factory),
        subject_incompatible_same_half_day_optional(constraint_factory),
        subject_incompatible_same_day_mandatory(constraint_factory),
        subject_incompatible_same_day_optional(constraint_factory),
        subject_incompatible_two_consecutive_days_mandatory(constraint_factory),
        subject_incompatible_two_consecutive_days_optional(constraint_factory),
        subject_prevent_consecutive_mandatory(constraint_factory),
        subject_prevent_consecutive_optional(constraint_factory),
        subject_weekly_order_mandatory(constraint_factory),
        subject_weekly_order_optional(constraint_factory),
        subject_max_separation_successive_days_mandatory(constraint_factory),
        subject_max_separation_successive_days_optional(constraint_factory),
        subject_group_course_order_group_before_mandatory(constraint_factory),
        subject_group_course_order_group_before_optional(constraint_factory),
        subject_group_course_order_group_after_mandatory(constraint_factory),
        subject_group_course_order_group_after_optional(constraint_factory),
        subject_group_course_order_group_before_or_after_mandatory(constraint_factory),
        subject_group_course_order_group_before_or_after_optional(constraint_factory),
        subject_group_course_order_group_before_or_after_fortnight_mandatory(constraint_factory),
        subject_group_course_order_group_before_or_after_fortnight_optional(constraint_factory),
    ]


def _courses_overlap_in_time(c1, c2):
    if c1.timeslot is None or c2.timeslot is None:
        return False
    start1 = c1.timeslot.minutes_from_midnight
    end1 = start1 + c1.duration_minutes
    start2 = c2.timeslot.minutes_from_midnight
    end2 = start2 + c2.duration_minutes
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
    Pour éviter que l'algorithme ne laisse tous les cours non assignés,
    on applique une pénalité dure (ONE_HARD) à chaque cours non assigné.
    Comme un conflit dur et une non-assignation coûtent le même prix (-1 Hard),
    le solveur peut transiter par des états intermédiaires de conflit pour trouver la solution optimale.
    """
    return (
        constraint_factory.for_each_including_unassigned(PlanningCourse)
        .filter(lambda c: getattr(c, 'timeslot', None) is None)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Pénaliser les cours non assignés (Overconstrained Planning)")
    )


# ==========================================
# 1. CONTRAINTES DURES (HardScore)
# ==========================================

def course_day_overflow(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None)
        .filter(lambda course: course.timeslot.minutes_from_midnight + course.duration_minutes > course.timeslot.absolute_end_of_day)
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
        .filter(lambda course1, course2: periods_overlap(course1.period_mask, course2.period_mask))
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
        .filter(lambda course1, course2: periods_overlap(course1.period_mask, course2.period_mask))
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
        .filter(lambda course1, course2: periods_overlap(course1.period_mask, course2.period_mask))
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
        .filter(lambda course1, course2: periods_overlap(course1.period_mask, course2.period_mask))
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
        .filter(lambda link, course1, course2: periods_overlap(course1.period_mask, course2.period_mask))
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
        .filter(lambda course1, course2: course1.timeslot is not None and course2.timeslot is not None and abs(course1.timeslot.minutes_from_midnight - course2.timeslot.minutes_from_midnight) == course1.duration_minutes)
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
        .filter(lambda course1, course2: course1.timeslot is not None and course2.timeslot is not None and abs(course1.timeslot.minutes_from_midnight - course2.timeslot.minutes_from_midnight) == course1.duration_minutes)
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
        .filter(lambda course1, course2: course1.timeslot is not None and course2.timeslot is not None and abs(course1.timeslot.minutes_from_midnight - course2.timeslot.minutes_from_midnight) == course1.duration_minutes)
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
        .filter(lambda course, pref: pref.preference_level == "Unsuited" and weeks_overlap(course.week_type, pref.week_type) and periods_overlap(course.period_mask, pref.period_mask))
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
        .filter(lambda course, pref: pref.preference_level == "Undesirable" and weeks_overlap(course.week_type, pref.week_type) and periods_overlap(course.period_mask, pref.period_mask))
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
        .filter(lambda course, pref: pref.preference_level == "Preferred" and weeks_overlap(course.week_type, pref.week_type) and periods_overlap(course.period_mask, pref.period_mask))
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
    for d1 in c1.all_division_ids:
        if d1 in c2.all_division_ids:
            return True
    return False

def _courses_match_rc_divisions(c1, c2, rc):
    """Vérifie si les deux cours partagent une division dans le périmètre de la contrainte.
    Si rc.division_ids est vide, on vérifie juste qu'ils partagent au moins une division (toutes classes).
    Sinon, on vérifie qu'ils partagent une division qui est dans la liste."""
    if len(rc.division_ids) == 0:
        return _courses_share_division(c1, c2)
    for d1 in c1.all_division_ids:
        if d1 in rc.division_ids:
            if d1 in c2.all_division_ids:
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
    elif pref.resource_type == "Course":
        return course.id == pref.resource_id
    elif pref.resource_type == "NonTeachingStaff":
        for s in course.non_teaching_staffs:
            if s.id == pref.resource_id:
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
        .filter(lambda teacher, course: course.timeslot is not None and course.timeslot.minutes_from_midnight < course.timeslot.noon_boundary_minutes)
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
        .filter(lambda teacher, course: course.timeslot is not None and course.timeslot.minutes_from_midnight >= course.timeslot.noon_boundary_minutes)
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
        .filter(lambda teacher_id, day, timeslots_set: any(ts.minutes_from_midnight < ts.noon_boundary_minutes for ts in timeslots_set) and any(ts.minutes_from_midnight >= ts.noon_boundary_minutes for ts in timeslots_set))
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
        .filter(lambda teacher_id, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight < time_to_minutes(rc.late_start_time)}) > (5 - rc.late_start_days_per_week))
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight < time_to_minutes(rc.late_start_time)}) - (5 - rc.late_start_days_per_week)) * 10)
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
        .filter(lambda teacher_id, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight >= time_to_minutes(rc.early_end_time)}) > (5 - rc.early_end_days_per_week))
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight >= time_to_minutes(rc.early_end_time)}) - (5 - rc.early_end_days_per_week)) * 10)
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
        .filter(lambda teacher_id, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight < ts.noon_boundary_minutes}) > rc.max_worked_am_per_week)
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight < ts.noon_boundary_minutes}) - rc.max_worked_am_per_week) * 10)
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
        .filter(lambda teacher_id, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight >= ts.noon_boundary_minutes}) > rc.max_worked_pm_per_week)
        .penalize(HardSoftScore.ONE_HARD, lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight >= ts.noon_boundary_minutes}) - rc.max_worked_pm_per_week) * 10)
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
        .filter(lambda division, course: course.timeslot is not None and course.timeslot.minutes_from_midnight < course.timeslot.noon_boundary_minutes)
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
        .filter(lambda division, course: course.timeslot is not None and course.timeslot.minutes_from_midnight >= course.timeslot.noon_boundary_minutes)
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


def division_max_pedagogic_weight_per_day(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningDivision)
        .filter(lambda division: division.max_pedagogic_weight_per_day is not None)
        .join(PlanningCourse, Joiners.filtering(_course_has_division))
        .filter(lambda division, course: course.timeslot is not None)
        .group_by(
            lambda division, course: division,
            lambda division, course: course.timeslot.day_of_week,
            ConstraintCollectors.sum(lambda division, course: int(course.pedagogic_weight_total * 10))
        )
        .filter(lambda division, day, total_weight_int: total_weight_int > int(division.max_pedagogic_weight_per_day * 10))
        .penalize(HardSoftScore.ONE_HARD, lambda division, day, total_weight_int: total_weight_int - int(division.max_pedagogic_weight_per_day * 10))
        .as_constraint("Division max pedagogic weight per day")
    )

def division_max_pedagogic_weight_per_am(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningDivision)
        .filter(lambda division: division.max_pedagogic_weight_per_morning is not None)
        .join(PlanningCourse, Joiners.filtering(_course_has_division))
        .filter(lambda division, course: course.timeslot is not None and course.timeslot.minutes_from_midnight < course.timeslot.noon_boundary_minutes)
        .group_by(
            lambda division, course: division,
            lambda division, course: course.timeslot.day_of_week,
            ConstraintCollectors.sum(lambda division, course: int(course.pedagogic_weight_total * 10))
        )
        .filter(lambda division, day, total_weight_int: total_weight_int > int(division.max_pedagogic_weight_per_morning * 10))
        .penalize(HardSoftScore.ONE_HARD, lambda division, day, total_weight_int: total_weight_int - int(division.max_pedagogic_weight_per_morning * 10))
        .as_constraint("Division max pedagogic weight per morning")
    )

def division_max_pedagogic_weight_per_pm(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningDivision)
        .filter(lambda division: division.max_pedagogic_weight_per_afternoon is not None)
        .join(PlanningCourse, Joiners.filtering(_course_has_division))
        .filter(lambda division, course: course.timeslot is not None and course.timeslot.minutes_from_midnight >= course.timeslot.noon_boundary_minutes)
        .group_by(
            lambda division, course: division,
            lambda division, course: course.timeslot.day_of_week,
            ConstraintCollectors.sum(lambda division, course: int(course.pedagogic_weight_total * 10))
        )
        .filter(lambda division, day, total_weight_int: total_weight_int > int(division.max_pedagogic_weight_per_afternoon * 10))
        .penalize(HardSoftScore.ONE_HARD, lambda division, day, total_weight_int: total_weight_int - int(division.max_pedagogic_weight_per_afternoon * 10))
        .as_constraint("Division max pedagogic weight per afternoon")
    )


def _is_not_chronologically_before(c1: PlanningCourse, c2: PlanningCourse) -> bool:
    if c1.timeslot is None or c2.timeslot is None:
        return False
    if c1.timeslot.day_of_week > c2.timeslot.day_of_week:
        return True
    if c1.timeslot.day_of_week == c2.timeslot.day_of_week:
        return c1.timeslot.minutes_from_midnight >= c2.timeslot.minutes_from_midnight
    return False


def _are_consecutive(c1: PlanningCourse, c2: PlanningCourse) -> bool:
    if c1.timeslot is None or c2.timeslot is None:
        return False
    if c1.timeslot.day_of_week != c2.timeslot.day_of_week:
        return False
    if not weeks_overlap(c1.week_type, c2.week_type):
        return False
    t1 = c1.timeslot.minutes_from_midnight
    t2 = c2.timeslot.minutes_from_midnight
    if t1 + c1.duration_minutes == t2:
        return True
    if t2 + c2.duration_minutes == t1:
        return True
    return False


def _share_reference_period(c1: PlanningCourse, c2: PlanningCourse, scope: str, custom_half_days: typing.Optional[int] = None) -> bool:
    if c1.timeslot is None or c2.timeslot is None:
        return False
    
    if scope == "QUINZAINE":
        # Même quinzaine / même alternance de semaine (A vs B)
        return c1.week_type == c2.week_type or c1.week_type == "W" or c2.week_type == "W"
        
    if not weeks_overlap(c1.week_type, c2.week_type):
        return False
        
    if not periods_overlap(c1.period_mask, c2.period_mask):
        return False
        
    if scope == "SLOT":
        return c1.timeslot.id == c2.timeslot.id
    elif scope == "DAY":
        return c1.timeslot.day_of_week == c2.timeslot.day_of_week
    elif scope == "HALF_DAY":
        c1_am = c1.timeslot.minutes_from_midnight < c1.timeslot.noon_boundary_minutes
        c2_am = c2.timeslot.minutes_from_midnight < c2.timeslot.noon_boundary_minutes
        return c1.timeslot.day_of_week == c2.timeslot.day_of_week and c1_am == c2_am
    elif scope == "CUSTOM_HALF_DAYS":
        n = custom_half_days if custom_half_days is not None and custom_half_days > 0 else 1
        c1_hd = (c1.timeslot.day_of_week - 1) * 2 + (0 if c1.timeslot.minutes_from_midnight < c1.timeslot.noon_boundary_minutes else 1)
        c2_hd = (c2.timeslot.day_of_week - 1) * 2 + (0 if c2.timeslot.minutes_from_midnight < c2.timeslot.noon_boundary_minutes else 1)
        return (c1_hd // n) == (c2_hd // n)
    return False


def course_to_course_force_same_scope_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourseToCourseConstraint)
        .filter(lambda ctc: ctc.type == "FORCE_SAME_SCOPE" and not ctc.is_optional)
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c: c.id in ctc.course_ids and c.timeslot is not None)
        )
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c1, c2: c2.id in ctc.course_ids and c1.id < c2.id and c2.timeslot is not None)
        )
        .filter(lambda ctc, c1, c2: not _share_reference_period(c1, c2, ctc.scope, ctc.custom_half_days))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Course-to-course force same scope mandatory")
    )


def course_to_course_force_same_scope_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourseToCourseConstraint)
        .filter(lambda ctc: ctc.type == "FORCE_SAME_SCOPE" and ctc.is_optional)
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c: c.id in ctc.course_ids and c.timeslot is not None)
        )
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c1, c2: c2.id in ctc.course_ids and c1.id < c2.id and c2.timeslot is not None)
        )
        .filter(lambda ctc, c1, c2: not _share_reference_period(c1, c2, ctc.scope, ctc.custom_half_days))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Course-to-course force same scope optional")
    )


def course_to_course_forbid_same_scope_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourseToCourseConstraint)
        .filter(lambda ctc: ctc.type == "FORBID_SAME_SCOPE" and not ctc.is_optional)
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c: c.id in ctc.course_ids and c.timeslot is not None)
        )
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c1, c2: c2.id in ctc.course_ids and c1.id < c2.id and c2.timeslot is not None)
        )
        .filter(lambda ctc, c1, c2: _share_reference_period(c1, c2, ctc.scope, ctc.custom_half_days))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Course-to-course forbid same scope mandatory")
    )


def course_to_course_forbid_same_scope_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourseToCourseConstraint)
        .filter(lambda ctc: ctc.type == "FORBID_SAME_SCOPE" and ctc.is_optional)
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c: c.id in ctc.course_ids and c.timeslot is not None)
        )
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c1, c2: c2.id in ctc.course_ids and c1.id < c2.id and c2.timeslot is not None)
        )
        .filter(lambda ctc, c1, c2: _share_reference_period(c1, c2, ctc.scope, ctc.custom_half_days))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Course-to-course forbid same scope optional")
    )


def course_to_course_order_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourseToCourseConstraint)
        .filter(lambda ctc: ctc.type == "ORDER" and not ctc.is_optional)
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c: c.id in ctc.course_ids and c.timeslot is not None)
        )
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c1, c2: c2.id in ctc.course_ids and c2.timeslot is not None)
        )
        .filter(lambda ctc, c1, c2: ctc.course_ids.index(c1.id) < ctc.course_ids.index(c2.id))
        .filter(lambda ctc, c1, c2: _is_not_chronologically_before(c1, c2))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Course-to-course order mandatory")
    )


def course_to_course_order_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourseToCourseConstraint)
        .filter(lambda ctc: ctc.type == "ORDER" and ctc.is_optional)
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c: c.id in ctc.course_ids and c.timeslot is not None)
        )
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c1, c2: c2.id in ctc.course_ids and c2.timeslot is not None)
        )
        .filter(lambda ctc, c1, c2: ctc.course_ids.index(c1.id) < ctc.course_ids.index(c2.id))
        .filter(lambda ctc, c1, c2: _is_not_chronologically_before(c1, c2))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Course-to-course order optional")
    )


def course_to_course_forbid_consecutive_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourseToCourseConstraint)
        .filter(lambda ctc: ctc.type == "FORBID_CONSECUTIVE" and not ctc.is_optional)
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c: c.id in ctc.course_ids and c.timeslot is not None)
        )
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c1, c2: c2.id in ctc.course_ids and c1.id < c2.id and c2.timeslot is not None)
        )
        .filter(lambda ctc, c1, c2: _are_consecutive(c1, c2))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Course-to-course forbid consecutive mandatory")
    )


def course_to_course_forbid_consecutive_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourseToCourseConstraint)
        .filter(lambda ctc: ctc.type == "FORBID_CONSECUTIVE" and ctc.is_optional)
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c: c.id in ctc.course_ids and c.timeslot is not None)
        )
        .join(
            PlanningCourse,
            Joiners.filtering(lambda ctc, c1, c2: c2.id in ctc.course_ids and c1.id < c2.id and c2.timeslot is not None)
        )
        .filter(lambda ctc, c1, c2: _are_consecutive(c1, c2))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Course-to-course forbid consecutive optional")
    )




# ==========================================
# 9. SUBJECT SPECIFIC CONSTRAINTS
# ==========================================

def subject_default_incompatible_same_day(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None and c.subject_id is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type),
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None)
        .filter(lambda c1, c2: _courses_share_division(c1, c2))
        .filter(lambda c1, c2: _share_reference_period(c1, c2, "DAY"))
        .if_not_exists(
            PlanningResourceConstraint,
            Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type),
            # Note d'architecture : Lors de la construction du PlanningProblem dans solver.py, 
            # l'attribut ORM 'target_subject_a_id' est dynamiquement mappé dans la propriété 'resource_id' 
            # de PlanningResourceConstraint pour unifier le modèle en RAM.
            Joiners.equal(lambda c1, c2: c1.subject_id, lambda rc: rc.resource_id),
            Joiners.equal(lambda c1, c2: c2.subject_id, lambda rc: rc.target_subject_b_id),
            Joiners.filtering(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        )
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Default Incompatible Same Day")
    )

def subject_incompatible_same_half_day_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None)
        
        .filter(lambda c1, c2: _share_reference_period(c1, c2, "HALF_DAY"))
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type))
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.incompatible_same_half_day is True and not rc.is_optional)
        .filter(lambda c1, c2, rc: (c1.subject_id == rc.resource_id and c2.subject_id == rc.target_subject_b_id) or (c2.subject_id == rc.resource_id and c1.subject_id == rc.target_subject_b_id))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Incompatible Same Half Day Mandatory")
    )

def subject_incompatible_same_half_day_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None)
        
        .filter(lambda c1, c2: _share_reference_period(c1, c2, "HALF_DAY"))
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type))
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.incompatible_same_half_day is True and rc.is_optional)
        .filter(lambda c1, c2, rc: (c1.subject_id == rc.resource_id and c2.subject_id == rc.target_subject_b_id) or (c2.subject_id == rc.resource_id and c1.subject_id == rc.target_subject_b_id))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Subject Incompatible Same Half Day Optional")
    )

def subject_incompatible_same_day_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None)
        
        .filter(lambda c1, c2: _share_reference_period(c1, c2, "DAY"))
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type))
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.incompatible_same_day is True and not rc.is_optional)
        .filter(lambda c1, c2, rc: (c1.subject_id == rc.resource_id and c2.subject_id == rc.target_subject_b_id) or (c2.subject_id == rc.resource_id and c1.subject_id == rc.target_subject_b_id))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Incompatible Same Day Mandatory")
    )

def subject_incompatible_same_day_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None)
        
        .filter(lambda c1, c2: _share_reference_period(c1, c2, "DAY"))
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type))
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.incompatible_same_day is True and rc.is_optional)
        .filter(lambda c1, c2, rc: (c1.subject_id == rc.resource_id and c2.subject_id == rc.target_subject_b_id) or (c2.subject_id == rc.resource_id and c1.subject_id == rc.target_subject_b_id))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Subject Incompatible Same Day Optional")
    )

def subject_incompatible_two_consecutive_days_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None)
        
        .filter(lambda c1, c2: abs(c1.timeslot.day_of_week - c2.timeslot.day_of_week) <= 1)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type))
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.incompatible_two_consecutive_days is True and not rc.is_optional)
        .filter(lambda c1, c2, rc: (c1.subject_id == rc.resource_id and c2.subject_id == rc.target_subject_b_id) or (c2.subject_id == rc.resource_id and c1.subject_id == rc.target_subject_b_id))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Incompatible Two Consecutive Days Mandatory")
    )

def subject_incompatible_two_consecutive_days_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None)
        
        .filter(lambda c1, c2: abs(c1.timeslot.day_of_week - c2.timeslot.day_of_week) <= 1)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type))
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.incompatible_two_consecutive_days is True and rc.is_optional)
        .filter(lambda c1, c2, rc: (c1.subject_id == rc.resource_id and c2.subject_id == rc.target_subject_b_id) or (c2.subject_id == rc.resource_id and c1.subject_id == rc.target_subject_b_id))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Subject Incompatible Two Consecutive Days Optional")
    )

def subject_prevent_consecutive_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type))
        .filter(lambda c1, c2: c1.id != c2.id and c2.timeslot is not None)
        
        .filter(lambda c1, c2: _are_consecutive(c1, c2))
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type))
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: not rc.is_optional and (
            (rc.prevent_consecutive_a_then_b is True and c1.subject_id == rc.resource_id and c2.subject_id == rc.target_subject_b_id) or
            (rc.prevent_consecutive_b_then_a is True and c1.subject_id == rc.target_subject_b_id and c2.subject_id == rc.resource_id)
        ))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Prevent Consecutive A then B or B then A Mandatory")
    )

def subject_prevent_consecutive_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type))
        .filter(lambda c1, c2: c1.id != c2.id and c2.timeslot is not None)
        
        .filter(lambda c1, c2: _are_consecutive(c1, c2))
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type))
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.is_optional and (
            (rc.prevent_consecutive_a_then_b is True and c1.subject_id == rc.resource_id and c2.subject_id == rc.target_subject_b_id) or
            (rc.prevent_consecutive_b_then_a is True and c1.subject_id == rc.target_subject_b_id and c2.subject_id == rc.resource_id)
        ))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Subject Prevent Consecutive A then B or B then A Optional")
    )

def subject_weekly_order_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type))
        .filter(lambda c1, c2: c1.id != c2.id and c2.timeslot is not None)
        
        .filter(lambda c1, c2: not _is_not_chronologically_before(c1, c2))
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type))
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: not rc.is_optional and (
            (rc.weekly_order == "B_BEFORE_A" and c1.subject_id == rc.resource_id and c2.subject_id == rc.target_subject_b_id) or
            (rc.weekly_order == "A_BEFORE_B" and c1.subject_id == rc.target_subject_b_id and c2.subject_id == rc.resource_id)
        ))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Weekly Order Mandatory")
    )

def subject_weekly_order_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type))
        .filter(lambda c1, c2: c1.id != c2.id and c2.timeslot is not None)
        
        .filter(lambda c1, c2: not _is_not_chronologically_before(c1, c2))
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type))
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.is_optional and (
            (rc.weekly_order == "B_BEFORE_A" and c1.subject_id == rc.resource_id and c2.subject_id == rc.target_subject_b_id) or
            (rc.weekly_order == "A_BEFORE_B" and c1.subject_id == rc.target_subject_b_id and c2.subject_id == rc.resource_id)
        ))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Subject Weekly Order Optional")
    )

def subject_max_separation_successive_days_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type),
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type),
              Joiners.equal(lambda c1, c2: c1.subject_id, lambda rc: (rc.resource_id)))
        .filter(lambda c1, c2, rc: rc.resource_id == rc.target_subject_b_id)
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.max_separation == "SUCCESSIVE_DAYS" and not rc.is_optional)
        .filter(lambda c1, c2, rc: abs(c1.timeslot.day_of_week - c2.timeslot.day_of_week) > 1)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Max Separation Successive Days Mandatory")
    )

def subject_max_separation_successive_days_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type),
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type),
              Joiners.equal(lambda c1, c2: c1.subject_id, lambda rc: (rc.resource_id)))
        .filter(lambda c1, c2, rc: rc.resource_id == rc.target_subject_b_id)
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.max_separation == "SUCCESSIVE_DAYS" and rc.is_optional)
        .filter(lambda c1, c2, rc: abs(c1.timeslot.day_of_week - c2.timeslot.day_of_week) > 1)
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Subject Max Separation Successive Days Optional")
    )

def subject_group_course_order_group_before_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None and len(c.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type),
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c2.is_full_class and not c1.is_full_class and c2.timeslot is not None)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type),
              Joiners.equal(lambda c1, c2: c1.subject_id, lambda rc: (rc.resource_id)))
        .filter(lambda c1, c2, rc: rc.resource_id == rc.target_subject_b_id)
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.group_course_order == "GROUP_BEFORE" and not rc.is_optional)
        .filter(lambda c1, c2, rc: _is_not_chronologically_before(c1, c2))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Group Course Order Group Before Mandatory")
    )

def subject_group_course_order_group_before_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None and len(c.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type),
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c2.is_full_class and not c1.is_full_class and c2.timeslot is not None)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type),
              Joiners.equal(lambda c1, c2: c1.subject_id, lambda rc: (rc.resource_id)))
        .filter(lambda c1, c2, rc: rc.resource_id == rc.target_subject_b_id)
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.group_course_order == "GROUP_BEFORE" and rc.is_optional)
        .filter(lambda c1, c2, rc: _is_not_chronologically_before(c1, c2))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Subject Group Course Order Group Before Optional")
    )

def subject_group_course_order_group_after_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None and len(c.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type),
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c2.is_full_class and not c1.is_full_class and c2.timeslot is not None)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type),
              Joiners.equal(lambda c1, c2: c1.subject_id, lambda rc: (rc.resource_id)))
        .filter(lambda c1, c2, rc: rc.resource_id == rc.target_subject_b_id)
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.group_course_order == "GROUP_AFTER" and not rc.is_optional)
        .filter(lambda c1, c2, rc: _is_not_chronologically_before(c2, c1))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Group Course Order Group After Mandatory")
    )

def subject_group_course_order_group_after_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None and len(c.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.week_type),
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c2.is_full_class and not c1.is_full_class and c2.timeslot is not None)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2: "Subject", lambda rc: rc.resource_type),
              Joiners.equal(lambda c1, c2: c1.subject_id, lambda rc: (rc.resource_id)))
        .filter(lambda c1, c2, rc: rc.resource_id == rc.target_subject_b_id)
        .filter(lambda c1, c2, rc: _courses_match_rc_divisions(c1, c2, rc))
        .filter(lambda c1, c2, rc: rc.group_course_order == "GROUP_AFTER" and rc.is_optional)
        .filter(lambda c1, c2, rc: _is_not_chronologically_before(c2, c1))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Subject Group Course Order Group After Optional")
    )

def subject_group_course_order_group_before_or_after_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None and len(c.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None and len(c2.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c1, c2: c1.subject_id, lambda c3: c3.subject_id))
        .filter(lambda c1, c2, c3: c3.timeslot is not None and c3.is_full_class and not c1.is_full_class and not c2.is_full_class)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2, c3: "Subject", lambda rc: rc.resource_type),
              Joiners.equal(lambda c1, c2, c3: c1.subject_id, lambda rc: rc.resource_id))
        .filter(lambda c1, c2, c3, rc: rc.resource_id == rc.target_subject_b_id)
        .filter(lambda c1, c2, c3, rc: _courses_match_rc_divisions(c1, c3, rc) and _courses_match_rc_divisions(c2, c3, rc))
        .filter(lambda c1, c2, c3, rc: rc.group_course_order == "GROUP_BEFORE_OR_AFTER" and not rc.is_optional)
        .filter(lambda c1, c2, c3, rc: 
            (not _is_not_chronologically_before(c1, c3) and not _is_not_chronologically_before(c3, c2)) or
            (not _is_not_chronologically_before(c2, c3) and not _is_not_chronologically_before(c3, c1))
        )
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Group Course Order Group Before Or After Mandatory")
    )

def subject_group_course_order_group_before_or_after_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None and len(c.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None and len(c2.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c1, c2: c1.subject_id, lambda c3: c3.subject_id))
        .filter(lambda c1, c2, c3: c3.timeslot is not None and c3.is_full_class and not c1.is_full_class and not c2.is_full_class)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2, c3: "Subject", lambda rc: rc.resource_type),
              Joiners.equal(lambda c1, c2, c3: c1.subject_id, lambda rc: rc.resource_id))
        .filter(lambda c1, c2, c3, rc: rc.resource_id == rc.target_subject_b_id)
        .filter(lambda c1, c2, c3, rc: _courses_match_rc_divisions(c1, c3, rc) and _courses_match_rc_divisions(c2, c3, rc))
        .filter(lambda c1, c2, c3, rc: rc.group_course_order == "GROUP_BEFORE_OR_AFTER" and rc.is_optional)
        .filter(lambda c1, c2, c3, rc: 
            (not _is_not_chronologically_before(c1, c3) and not _is_not_chronologically_before(c3, c2)) or
            (not _is_not_chronologically_before(c2, c3) and not _is_not_chronologically_before(c3, c1))
        )
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Subject Group Course Order Group Before Or After Optional")
    )

def subject_group_course_order_group_before_or_after_fortnight_mandatory(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None and len(c.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None and len(c2.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c1, c2: c1.subject_id, lambda c3: c3.subject_id))
        .filter(lambda c1, c2, c3: c3.timeslot is not None and c3.is_full_class and not c1.is_full_class and not c2.is_full_class)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2, c3: "Subject", lambda rc: rc.resource_type),
              Joiners.equal(lambda c1, c2, c3: c1.subject_id, lambda rc: rc.resource_id))
        .filter(lambda c1, c2, c3, rc: rc.resource_id == rc.target_subject_b_id)
        .filter(lambda c1, c2, c3, rc: _courses_match_rc_divisions(c1, c3, rc) and _courses_match_rc_divisions(c2, c3, rc))
        .filter(lambda c1, c2, c3, rc: rc.group_course_order == "GROUP_BEFORE_OR_AFTER_FORTNIGHT" and not rc.is_optional)
        .filter(lambda c1, c2, c3, rc: 
            (not _is_not_chronologically_before(c1, c3) and not _is_not_chronologically_before(c2, c3)) or
            (not _is_not_chronologically_before(c3, c1) and not _is_not_chronologically_before(c3, c2))
        )
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Subject Group Course Order Group Before Or After Fortnight Mandatory")
    )

def subject_group_course_order_group_before_or_after_fortnight_optional(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda c: c.timeslot is not None and len(c.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c: c.subject_id))
        .filter(lambda c1, c2: c1.id < c2.id and c2.timeslot is not None and len(c2.class_part_ids) > 0)
        .join(PlanningCourse,
              Joiners.equal(lambda c1, c2: c1.subject_id, lambda c3: c3.subject_id))
        .filter(lambda c1, c2, c3: c3.timeslot is not None and c3.is_full_class and not c1.is_full_class and not c2.is_full_class)
        .join(PlanningResourceConstraint,
              Joiners.equal(lambda c1, c2, c3: "Subject", lambda rc: rc.resource_type),
              Joiners.equal(lambda c1, c2, c3: c1.subject_id, lambda rc: rc.resource_id))
        .filter(lambda c1, c2, c3, rc: rc.resource_id == rc.target_subject_b_id)
        .filter(lambda c1, c2, c3, rc: _courses_match_rc_divisions(c1, c3, rc) and _courses_match_rc_divisions(c2, c3, rc))
        .filter(lambda c1, c2, c3, rc: rc.group_course_order == "GROUP_BEFORE_OR_AFTER_FORTNIGHT" and rc.is_optional)
        .filter(lambda c1, c2, c3, rc: 
            (not _is_not_chronologically_before(c1, c3) and not _is_not_chronologically_before(c2, c3)) or
            (not _is_not_chronologically_before(c3, c1) and not _is_not_chronologically_before(c3, c2))
        )
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Subject Group Course Order Group Before Or After Fortnight Optional")
    )





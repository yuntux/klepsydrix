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

# La JVM démarre ICI (premier `ensure_init()` réellement atteint dans tout le code — vérifié
# empiriquement : `import timefold.solver`/`timefold.solver.config` seuls ne la démarrent PAS,
# JPype le fait uniquement au premier `ensure_init()` explicite). Par défaut, Timefold la démarre
# sans arguments particuliers — un crash JVM (ex: bug natif de la JVM elle-même, jamais vu en
# pratique mais possible) écrirait alors un `hs_err_pid<N>.log` dans le répertoire COURANT du
# process (la racine du dépôt, voir start_services.sh — uvicorn y est lancé sans `cd` préalable),
# jamais nettoyé ; et sans `-Xmx` explicite, la JVM (partagée par TOUTES les résolutions du
# process, voir solver.py) se laisse par défaut jusqu'à 1/4 de la RAM de la machine — un risque de
# swap si plusieurs résolutions volumineuses tournent en même temps (voir architecture.md,
# "Concurrence des résolutions"). `timefold.solver.init(...)`, appelé explicitement AVANT ce
# `ensure_init()` (qui lève `RuntimeError` si appelé après que la JVM a démarré), permet de fixer
# les deux (`-XX:ErrorFile=...`, `-Xmx...`).
import jpype
if not jpype.isJVMStarted():
    from pathlib import Path
    from _jpyinterpreter import get_default_jvm_path
    import timefold.solver
    from backend.app.core.config import settings

    _jvm_log_dir = Path(__file__).resolve().parents[3] / "log_jvm"
    _jvm_log_dir.mkdir(exist_ok=True)
    timefold.solver.init(
        get_default_jvm_path(),
        f"-XX:ErrorFile={_jvm_log_dir}/hs_err_pid%p.log",
        f"-Xmx{settings.SOLVER_JVM_MAX_HEAP_MB}m",
    )

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
    # Optional : NULL = capacité illimitée (voir plan salles §1.1) — un simple `int` ici casse la
    # traduction bytecode Python->Java de Timefold (AttributeError côté Java) dès qu'une instance
    # porte capacity=None, vérifié empiriquement.
    capacity: typing.Optional[int] = None


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
    morning_break_minutes: typing.Optional[int] = None
    afternoon_break_minutes: typing.Optional[int] = None


# Fonctions nommées à arg scalaire/objet plutôt que propriétés sur PlanningTimeslot — même
# précaution déjà en place dans room_constraints.py (_rooms_overlap, _pair_bounds...). Une
# @property a d'abord été essayée ici : mesurablement plus lente à l'évaluation (franchissement
# JPype d'un appel de méthode plutôt qu'un accès de champ), au point de faire échouer un test
# solveur borné en temps (CH terminée prématurément, cours non placé).
#
# PIÈGE JPype confirmé en écrivant ce fichier (RuntimeError Java "X does not exist in global
# scope") : ces fonctions sont sûres à appeler depuis un lambda SIMPLE passé à Timefold (voir
# _share_reference_period plus bas, qui les appelle en cascade), y compris depuis une lambda de
# 2 niveaux — mais PAS depuis l'intérieur d'une generator/set-comprehension elle-même passée à
# Timefold (`any(_is_morning(ts) for ts in ...)`, `{... for ts in ... if _is_morning(ts)}`) :
# jpyinterpreter échoue alors à résoudre le nom de la fonction à l'exécution. Dans ce cas précis,
# revenir à la comparaison inline (`ts.minutes_from_midnight < ts.noon_boundary_minutes`) au lieu
# d'appeler la fonction — voir teacher_max_worked_am/pm plus bas pour l'exemple.
def _is_morning(ts: PlanningTimeslot) -> bool:
    return ts.minutes_from_midnight < ts.noon_boundary_minutes


def _half_day_index(ts: PlanningTimeslot) -> int:
    """Index de demi-journée sur la semaine (0 = lundi matin, 1 = lundi après-midi, 2 = mardi
    matin, ...) — utilisé par les contraintes CUSTOM_HALF_DAYS."""
    return (ts.day_of_week - 1) * 2 + (0 if _is_morning(ts) else 1)


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

@dataclass
class PlanningGroupDemand:
    """
    Fait (pas une entité) : le besoin d'un cours PARENT en salles d'un groupe donné — voir plan
    salles §2.1. `needed_count` = quantity de la ligne CourseClassroomRequirement du parent
    pointant vers ce groupe (déjà correcte grâce à la cascade décrémentée, pas une somme à
    recalculer ici). `group_leaf_ids` = salles-feuilles du groupe (classroom_closure.
    leaf_classroom_ids_under), calculé une fois à la construction du problème.
    """
    course_id: int
    demand_key: str
    group_id: int
    needed_count: int
    group_leaf_ids: List[int] = field(default_factory=list)


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
    is_pinned: Annotated[bool, PlanningPin] = False
    forbid_break_overlap: bool = False
    original_timeslot_id: typing.Optional[int] = None
    parent_id: typing.Optional[int] = None
    pedagogic_weight_total: float = 0.0
    # `classroom` n'est plus une @PlanningVariable de ce domaine (COURSE_PLACEMENT) — la salle
    # devient une ressource contrainte via leaf_classroom_ids/group_demands (voir plan salles
    # §2.1), résolue précisément dans le domaine séparé CLASSROOM_ASSIGNMENT (room_constraints.py).
    # Exigences sur salle-feuille précise, agrégées jusqu'au parent par la cascade de
    # CourseClassroomRequirement (course_classroom_requirement.py) — pas d'agrégation bespoke
    # nécessaire ici, une simple lecture directe des classroom_requirements du parent suffit.
    leaf_classroom_ids: List[int] = field(default_factory=list)
    
    # Alternance et parties de classe (US2)
    # week_type_range/week_type : voir Phase C, attribution_week_type_auto.md (Échanges 17-19).
    # Range scopé à l'ENTITÉ (contrairement à timeslotRange/classroomRange, scopés au problème
    # global) — vérifié possible par un spike dédié avant implémentation (Timefold 1.24.0b0 le
    # supporte nativement via un champ list[str] stocké, PAS une méthode calculée).
    # {"A","B"} pour tout cours dont le week_type BDD (c.week_type — pour un cours composé,
    # c'est l'agrégat _sync_parent_week_type de ses enfants) est A, B ou Q ; singleton = "W"
    # sinon. Grâce à la règle _sync_parent_week_type (un parent composé n'affiche A/B/Q QUE si
    # TOUS ses enfants partagent uniformément cette même valeur), un range libre est sûr même
    # pour un cours composé : la cascade au write-back (_write_back_course_placement) peut alors
    # reporter sans ambiguïté la lettre choisie à tous les enfants (voir Échange 18/19).
    # week_type=None pour un cours né Q : un spike dédié a confirmé qu'une valeur de départ hors
    # du range déclaré (ex: laisser "Q" alors que le range est ["A","B"]) n'est PAS réévaluée par
    # le solveur et peut rester bloquée telle quelle — None (comme timeslot/classroom ci-dessus)
    # est en revanche correctement pris en charge par la Construction Heuristic, avec un résultat
    # final identique, quelle que soit la valeur de départ légale choisie (même spike). Pour un
    # cours déjà résolu A/B, la valeur de départ reste sa valeur actuelle (point de départ naturel
    # pour la recherche, comme pour classroom — voir § 12.B d'architecture.md), pas None : rien
    # n'empêche le solveur de la faire quand même basculer si c'est meilleur.
    # @PlanningPin (is_pinned, ci-dessus) gèle cette variable exactement comme timeslot et
    # classroom, sans code dédié (vérifié par le même spike).
    week_type_range: Annotated[List[str], ValueRangeProvider(id='weekTypeRange')] = field(default_factory=lambda: ["W"])
    week_type: Annotated[typing.Optional[str], PlanningVariable(value_range_provider_refs=['weekTypeRange'])] = None
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
    divisions: Annotated[List[PlanningDivision], ProblemFactCollectionProperty]
    timeslots: Annotated[List[PlanningTimeslot], ProblemFactCollectionProperty, ValueRangeProvider(id='timeslotRange')]
    courses: Annotated[List[PlanningCourse], PlanningEntityCollectionProperty]
    class_part_links: Annotated[List[PlanningClassPartLink], ProblemFactCollectionProperty] = field(default_factory=list)
    preferences: Annotated[List[PlanningPreference], ProblemFactCollectionProperty] = field(default_factory=list)
    # Voir plan salles §2.1/§2.2 — remplace `classrooms`/`classroomRange` (salle plus une
    # PlanningVariable dans ce domaine).
    group_demands: Annotated[List[PlanningGroupDemand], ProblemFactCollectionProperty] = field(default_factory=list)
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
        leaf_classroom_conflict(constraint_factory),
        leaf_classroom_unsuited(constraint_factory),
        classroom_group_capacity(constraint_factory),
        division_conflict(constraint_factory),
        group_link_conflict(constraint_factory),
        course_day_overflow(constraint_factory),
        course_break_overlap(constraint_factory),
        stability_penalty(constraint_factory),
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
    Pour éviter que l'algorithme ne laisse tous les cours non assignés, on applique une
    pénalité dure à chaque cours non assigné — délibérément la plus faible de tout le domaine
    (ONE_HARD, jamais bumpée), voir la note de politique juste en dessous : le non-assigné doit
    toujours rester l'option la MOINS coûteuse, pour que le solveur préfère systématiquement
    laisser un cours non placé plutôt que de violer n'importe quelle autre contrainte dure.
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
# Politique de poids (revue complète) : toutes les contraintes dures de ce fichier sont en
# of_hard(1000), SAUF penalize_unassigned_course ci-dessus (ONE_HARD, jamais touchée — c'est la
# référence). Objectif : qu'un cours non placé coûte TOUJOURS strictement moins cher que n'importe
# quelle violation de contrainte dure, pour que le hill-climbing ait un gradient net vers "laisser
# non placé" plutôt qu'un mouvement latéral à score égal (voir l'historique de discussion : avant
# cette revue, seules leaf_classroom_unsuited/resource_preference_hard/course_break_overlap
# avaient ce traitement au cas par cas). Pour les contraintes à poids variable (ex:
# teacher_max_hours_per_day, pondérée par l'ampleur du dépassement × 10), seul le poids de base
# passe à of_hard(1000) — le multiplicateur par match (2ᵉ argument de .penalize) est inchangé, donc
# les proportions internes à chaque contrainte (1h de dépassement vs 3h) restent identiques,
# seulement mises à l'échelle globalement.

def course_day_overflow(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None)
        .filter(lambda course: course.timeslot.minutes_from_midnight + course.duration_minutes > course.timeslot.absolute_end_of_day)
        .penalize(HardSoftScore.of_hard(1000))
        .as_constraint("Course day overflow")
    )

def _course_overlaps_break_boundary(course) -> bool:
    """Option "Ne pas chevaucher les récréations" (Course.forbid_break_overlap) : la récréation
    n'est qu'un instant (pas de durée stockée, voir SystemSetting), donc chevaucher signifie
    contenir strictement cet instant — un cours qui démarre ou finit pile dessus est autorisé."""
    if course.timeslot is None or not course.forbid_break_overlap:
        return False
    start = course.timeslot.minutes_from_midnight
    end = start + course.duration_minutes
    morning = course.timeslot.morning_break_minutes
    if morning is not None and start < morning < end:
        return True
    afternoon = course.timeslot.afternoon_break_minutes
    if afternoon is not None and start < afternoon < end:
        return True
    return False

def course_break_overlap(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(_course_overlaps_break_boundary)
        # of_hard(1000), pas ONE_HARD : même raisonnement que leaf_classroom_unsuited/
        # resource_preference_hard ci-dessus — à égalité stricte avec penalize_unassigned_course
        # (ONE_HARD), rien ne pousserait le solveur à préférer laisser le cours non placé plutôt
        # que de violer l'option "Ne pas chevaucher les récréations" quand c'est le seul créneau
        # disponible.
        .penalize(HardSoftScore.of_hard(1000))
        .as_constraint("Course break overlap")
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
        .as_constraint("Non-teaching staff conflict")
    )

def _check_leaf_classroom_overlap(c1, c2):
    """Intersection non vide entre les deux listes de salles-feuilles exigées — factorisée en
    fonction nommée (pas un lambda avec generator expression) : le traducteur bytecode Python->
    Java de Timefold (JPype/jpyinterpreter) échoue sur une comprehension imbriquée dans un lambda
    (ClassCastException PythonCell), le même problème ne se produit pas avec une fonction
    top-level classique — mêmes contraintes que _check_division_overlap ci-dessus."""
    for i in c1.leaf_classroom_ids:
        if i in c2.leaf_classroom_ids:
            return True
    return False


def leaf_classroom_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    """
    Remplace classroom_conflict — salle n'est plus une PlanningVariable, un cours peut porter
    PLUSIEURS exigences de salle-feuille précise (leaf_classroom_ids), donc pas de Joiners.equal
    possible sur une valeur scalaire : on filtre sur l'intersection des deux listes. Mêmes 5
    conditions de chevauchement que l'ancienne contrainte (voir plan salles §2.2).
    """
    return (
        constraint_factory.for_each_unique_pair(
            PlanningCourse,
            Joiners.equal(lambda course: course.timeslot.day_of_week if course.timeslot is not None else -1)
        )
        .filter(lambda course1, course2: weeks_overlap(course1.week_type, course2.week_type))
        .filter(lambda course1, course2: periods_overlap(course1.period_mask, course2.period_mask))
        .filter(lambda course1, course2: hierarchy_overlap(course1, course2))
        .filter(_courses_overlap_in_time)
        .filter(_check_leaf_classroom_overlap)
        .penalize(HardSoftScore.of_hard(1000))
        .as_constraint("Leaf classroom conflict")
    )


def leaf_classroom_unsuited(constraint_factory: ConstraintFactory) -> Constraint:
    """
    Absorbe la part `resource_preference_hard` qui portait sur les salles (voir plan salles §2.2)
    : une salle-feuille précise frappée d'une préférence Unsuited pour le créneau/semaine/période
    du cours est une pénalité dure — _is_preference_violated ne gère plus jamais "Classroom"
    (voir plus bas), ce mirroir dédié le fait à sa place.

    ⚠️ `len(course.leaf_classroom_ids) > 0`, pas `bool(course.leaf_classroom_ids)` : constaté
    empiriquement en écrivant les tests dédiés (voir test_solver.py) que `bool()` appliqué à une
    liste Python à l'intérieur d'un lambda .filter() traduit par jpyinterpreter (Python->bytecode
    Java) évalue systématiquement à False, même liste non vide — la contrainte entière ne
    matchait jamais (0 résultat silencieux, aucune exception). `len(...) > 0` contourne le même
    problème que documenté pour PlanningClassroom.capacity plus haut : jpyinterpreter a des trous
    de couverture sur certains built-ins Python appliqués à des types collection.
    """
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and len(course.leaf_classroom_ids) > 0)
        .join(
            PlanningPreference,
            Joiners.equal(lambda course: course.timeslot.id, lambda pref: pref.timeslot_id)
        )
        .filter(lambda course, pref: pref.resource_type == "Classroom" and pref.preference_level == "Unsuited"
                and weeks_overlap(course.week_type, pref.week_type) and periods_overlap(course.period_mask, pref.period_mask))
        .filter(lambda course, pref: pref.resource_id in course.leaf_classroom_ids)
        # of_hard(1000), pas ONE_HARD : sinon strictement à égalité avec penalize_unassigned_course
        # (ONE_HARD lui aussi) — le solveur n'aurait alors AUCUNE préférence entre "placer quand
        # même le cours sur cette salle-feuille Unsuited" et "ne pas le placer du tout", et
        # pourrait très bien converger sur le premier (constaté : un hill-climbing ne fait pas de
        # mouvement latéral à score égal, rien ne le pousse vers l'option pourtant voulue). 1000
        # domine tout cumul réaliste de cours non placés à l'échelle d'un établissement.
        .penalize(HardSoftScore.of_hard(1000))
        .as_constraint("Leaf classroom unsuited")
    )


def _cluster_group_capacity_excess(group_id, rows) -> int:
    """
    Python pur, appelé depuis classroom_group_capacity ci-dessous (voir plan salles §2.2a/b et
    les spikes validés `spike_group_capacity.py`/`spike_group_capacity_unsuited_3way.py`) :
    regroupe les (demand, course, unsuited_leaf_id_ou_-1) d'un même groupe en clusters de
    créneaux qui se chevauchent réellement (union-find sur les 5 conditions), puis compare, par
    cluster, la somme des needed_count à la capacité du groupe MOINS les salles-feuilles exclues
    par une préférence Unsuited applicable à ce cluster. Retourne le nombre de clusters en excès
    (pas juste 0/1) — la pénalité est appliquée une fois par créneau-groupe en excès, confirmé.
    """
    if not rows:
        return 0
    total_leaf_rooms = len(rows[0][0].group_leaf_ids)

    by_demand_key = {}
    for demand, course, unsuited_leaf_id in rows:
        if course.timeslot is None:
            continue
        entry = by_demand_key.setdefault(demand.demand_key, {"demand": demand, "course": course, "unsuited": set()})
        if unsuited_leaf_id != -1:
            entry["unsuited"].add(unsuited_leaf_id)

    entries = list(by_demand_key.values())
    n = len(entries)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def overlap(e1, e2):
        c1, c2 = e1["course"], e2["course"]
        if c1.timeslot.day_of_week != c2.timeslot.day_of_week:
            return False
        if not weeks_overlap(c1.week_type, c2.week_type):
            return False
        if not periods_overlap(c1.period_mask, c2.period_mask):
            return False
        return _courses_overlap_in_time(c1, c2)

    for i in range(n):
        for j in range(i + 1, n):
            if overlap(entries[i], entries[j]):
                union(i, j)

    clusters = {}
    for i, e in enumerate(entries):
        root = find(i)
        c = clusters.setdefault(root, {"needed": 0, "unsuited": set()})
        c["needed"] += e["demand"].needed_count
        c["unsuited"] |= e["unsuited"]

    excess = 0
    for c in clusters.values():
        available = total_leaf_rooms - len(c["unsuited"])
        if c["needed"] > available:
            excess += 1
    return excess


def classroom_group_capacity(constraint_factory: ConstraintFactory) -> Constraint:
    """
    Cœur de la faisabilité des groupes (plan salles §2.2). Jointure à 3 (PlanningGroupDemand x
    PlanningCourse x PlanningPreference) validée par spike dédié : la préférence sentinelle
    (resource_id=-1, injectée une fois par _build_course_placement_problem) évite qu'une demande
    sans aucune salle Unsuited applicable disparaisse de la jointure (sinon jointure interne
    classique = perte de lignes).
    """
    return (
        constraint_factory.for_each(PlanningGroupDemand)
        .join(PlanningCourse, Joiners.equal(lambda d: d.course_id, lambda c: c.id))
        .filter(lambda d, c: c.timeslot is not None)
        .join(
            PlanningPreference,
            Joiners.filtering(lambda d, c, p: p.resource_id == -1 or (
                p.resource_type == "Classroom" and p.preference_level == "Unsuited"
                and p.resource_id in d.group_leaf_ids
                and p.timeslot_id == c.timeslot.id
                and weeks_overlap(c.week_type, p.week_type)
                and periods_overlap(c.period_mask, p.period_mask)
            ))
        )
        .group_by(
            lambda d, c, p: d.group_id,
            ConstraintCollectors.to_list(lambda d, c, p: (d, c, p.resource_id))
        )
        .filter(lambda group_id, rows: _cluster_group_capacity_excess(group_id, rows) > 0)
        .penalize(HardSoftScore.of_hard(1000), lambda group_id, rows: _cluster_group_capacity_excess(group_id, rows))
        .as_constraint("Classroom group capacity")
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
        .as_constraint("Group link conflict")
    )

def stability_penalty(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.original_timeslot_id is not None and course.timeslot is not None and course.original_timeslot_id != (course.timeslot.id if course.timeslot is not None else -1))
        .penalize(HardSoftScore.ONE_SOFT)
        .as_constraint("Minimize timetable disruption")
    )

# teacher_room_stability supprimée — dépendait de `classroom`, plus une PlanningVariable ici.
# Son équivalent (limiter les déplacements de salle d'un même professeur) vit désormais dans le
# domaine CLASSROOM_ASSIGNMENT (room_constraints.py, §3.0 du plan salles).

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
        # of_hard(1000), pas ONE_HARD : même raisonnement que leaf_classroom_unsuited ci-dessus —
        # sans ça, à égalité stricte avec penalize_unassigned_course (ONE_HARD), le solveur n'a
        # aucune préférence entre "placer quand même sur une ressource Unsuited (prof/division/
        # personnel)" et "ne pas placer le cours du tout". 1000 domine tout cumul réaliste.
        .penalize(HardSoftScore.of_hard(1000))
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
        # `classroom` n'est plus une PlanningVariable de PlanningCourse dans ce domaine
        # (COURSE_PLACEMENT) — jamais déclenchée ici. Absorbée par leaf_classroom_unsuited (salle
        # précise) et classroom_group_capacity (groupe), voir plan salles §2.2.
        return False
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
        .penalize(HardSoftScore.of_hard(1000), lambda teacher_id, day, count, rc: int((count - rc.max_hours_per_day) * 10))
        .as_constraint("Teacher max hours per day")
    )

def teacher_max_hours_per_am(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None and _is_morning(course.timeslot))
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
        .penalize(HardSoftScore.of_hard(1000), lambda teacher_id, day, count, rc: int((count - rc.max_hours_per_am) * 10))
        .as_constraint("Teacher max hours per morning")
    )

def teacher_max_hours_per_pm(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningTeacher)
        .join(PlanningCourse, Joiners.filtering(_course_has_teacher))
        .filter(lambda teacher, course: course.timeslot is not None and (not _is_morning(course.timeslot)))
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
        .penalize(HardSoftScore.of_hard(1000), lambda teacher_id, day, count, rc: int((count - rc.max_hours_per_pm) * 10))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000), lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight < time_to_minutes(rc.late_start_time)}) - (5 - rc.late_start_days_per_week)) * 10)
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
        .penalize(HardSoftScore.of_hard(1000), lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight >= time_to_minutes(rc.early_end_time)}) - (5 - rc.early_end_days_per_week)) * 10)
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
        .penalize(HardSoftScore.of_hard(1000), lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set}) - rc.max_presence_days_per_week) * 10)
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
        .penalize(HardSoftScore.of_hard(1000), lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set}) - (5 - rc.min_free_days_per_week)) * 10)
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
        .penalize(HardSoftScore.of_hard(1000), lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight < ts.noon_boundary_minutes}) - rc.max_worked_am_per_week) * 10)
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
        .penalize(HardSoftScore.of_hard(1000), lambda teacher_id, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.minutes_from_midnight >= ts.noon_boundary_minutes}) - rc.max_worked_pm_per_week) * 10)
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
        .penalize(HardSoftScore.of_hard(1000), lambda division_id, day, count, rc: int((count - rc.max_hours_per_day) * 10))
        .as_constraint("Division max hours per day")
    )

def division_max_hours_per_am(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningDivision)
        .join(PlanningCourse, Joiners.filtering(_course_has_division))
        .filter(lambda division, course: course.timeslot is not None and _is_morning(course.timeslot))
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
        .penalize(HardSoftScore.of_hard(1000), lambda division_id, day, count, rc: int((count - rc.max_hours_per_am) * 10))
        .as_constraint("Division max hours per morning")
    )

def division_max_hours_per_pm(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningDivision)
        .join(PlanningCourse, Joiners.filtering(_course_has_division))
        .filter(lambda division, course: course.timeslot is not None and (not _is_morning(course.timeslot)))
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
        .penalize(HardSoftScore.of_hard(1000), lambda division_id, day, count, rc: int((count - rc.max_hours_per_pm) * 10))
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
        .penalize(HardSoftScore.of_hard(1000), lambda division, day, total_weight_int: total_weight_int - int(division.max_pedagogic_weight_per_day * 10))
        .as_constraint("Division max pedagogic weight per day")
    )

def division_max_pedagogic_weight_per_am(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningDivision)
        .filter(lambda division: division.max_pedagogic_weight_per_morning is not None)
        .join(PlanningCourse, Joiners.filtering(_course_has_division))
        .filter(lambda division, course: course.timeslot is not None and _is_morning(course.timeslot))
        .group_by(
            lambda division, course: division,
            lambda division, course: course.timeslot.day_of_week,
            ConstraintCollectors.sum(lambda division, course: int(course.pedagogic_weight_total * 10))
        )
        .filter(lambda division, day, total_weight_int: total_weight_int > int(division.max_pedagogic_weight_per_morning * 10))
        .penalize(HardSoftScore.of_hard(1000), lambda division, day, total_weight_int: total_weight_int - int(division.max_pedagogic_weight_per_morning * 10))
        .as_constraint("Division max pedagogic weight per morning")
    )

def division_max_pedagogic_weight_per_pm(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningDivision)
        .filter(lambda division: division.max_pedagogic_weight_per_afternoon is not None)
        .join(PlanningCourse, Joiners.filtering(_course_has_division))
        .filter(lambda division, course: course.timeslot is not None and (not _is_morning(course.timeslot)))
        .group_by(
            lambda division, course: division,
            lambda division, course: course.timeslot.day_of_week,
            ConstraintCollectors.sum(lambda division, course: int(course.pedagogic_weight_total * 10))
        )
        .filter(lambda division, day, total_weight_int: total_weight_int > int(division.max_pedagogic_weight_per_afternoon * 10))
        .penalize(HardSoftScore.of_hard(1000), lambda division, day, total_weight_int: total_weight_int - int(division.max_pedagogic_weight_per_afternoon * 10))
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
        c1_am = _is_morning(c1.timeslot)
        c2_am = _is_morning(c2.timeslot)
        return c1.timeslot.day_of_week == c2.timeslot.day_of_week and c1_am == c2_am
    elif scope == "CUSTOM_HALF_DAYS":
        n = custom_half_days if custom_half_days is not None and custom_half_days > 0 else 1
        return (_half_day_index(c1.timeslot) // n) == (_half_day_index(c2.timeslot) // n)
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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
        .penalize(HardSoftScore.of_hard(1000))
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





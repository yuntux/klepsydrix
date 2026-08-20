"""
Domaine Timefold CLASSROOM_ASSIGNMENT (voir plan salles §3) — attribution des salles précises
au sein d'un groupe, une fois le placement horaire (COURSE_PLACEMENT, constraints.py) terminé.
Fichier séparé de constraints.py (déjà ~1600 lignes) — même style/conventions.

Pourquoi Timefold plutôt qu'un algorithme classique ici (§3.0 du plan, à reprendre tel quel dans
les spécifications) : sans la notion de continuité (limiter les déplacements de salle d'un même
professeur/d'une même division), ce serait un problème d'affectation biparti classique,
résoluble exactement par un algorithme de matching pondéré. La continuité couple les créneaux
entre eux (minimiser le nombre de salles distinctes par professeur n'est pas un coût additif par
affectation individuelle) — un algorithme classique la prenant en compte correctement (flot à
coûts fixes, ILP dédié) n'a plus rien de simple à écrire ni maintenir. Rester dans Timefold : (1)
les Constraint Streams expriment nativement ce type de contrainte molle transversale, (2) le
sous-problème reste petit (timeslot/week_type déjà figés par COURSE_PLACEMENT), (3) un seul
paradigme à faire évoluer dans le temps plutôt que deux.
"""
from dataclasses import dataclass, field
from typing import List, Annotated, Optional

from timefold.solver.domain import (
    planning_entity,
    planning_solution,
    PlanningVariable,
    PlanningId,
    ProblemFactCollectionProperty,
    PlanningEntityCollectionProperty,
    PlanningScore,
    ValueRangeProvider,
)
from timefold.solver.score import constraint_provider, ConstraintFactory, Joiners, Constraint, HardSoftScore, ConstraintCollectors

from backend.app.solver.constraints import (
    PlanningClassroom,
    PlanningPreference,
    weeks_overlap,
    periods_overlap,
)


@dataclass
class PlanningFixedRoomBooking:
    """
    Fait : occupation déjà connue d'une salle-feuille — soit une exigence salle-feuille précise
    d'un cours quelconque (parent ou enfant), soit une exigence de groupe déjà résolue par un run
    antérieur de CLASSROOM_ASSIGNMENT (write-back = mécanisme de sortie de domaine, voir §3.4).

    teacher_ids/division_ids (Phase 2 continuité, voir teacher_room_continuity_with_fixed_booking) :
    permettent de faire jouer la continuité de salle contre un cours dont la salle est déjà figée,
    pas seulement entre deux PlanningRoomAssignment en cours de résolution.
    """
    classroom_id: int
    day_of_week: int
    minutes_from_midnight: int
    duration_minutes: int
    week_type: str
    period_mask: int
    teacher_ids: List[int] = field(default_factory=list)
    division_ids: List[int] = field(default_factory=list)


@dataclass
class PlanningRoomOptimizationSettings:
    """
    Fait de configuration, choisi par l'utilisateur dans le wizard "Attribuer les salles" —
    toujours peuplé avec EXACTEMENT une instance (voir _build_classroom_assignment_problem) :
    un inner join contre une liste vide ferait disparaître silencieusement toute correspondance
    (piège déjà rencontré avec classroom_group_capacity), d'où l'assertion défensive côté
    construction plutôt qu'une valeur par défaut ici qui masquerait un oubli.
    """
    optimize_target: str = "TEACHER"  # "TEACHER" ou "DIVISION" — l'axe qui reçoit le poids ×10


@planning_entity
@dataclass
class PlanningRoomAssignment:
    id: Annotated[int, PlanningId]  # requirement.id * 100 + index d'unité (quantity <= 20)
    course_id: int
    day_of_week: int
    minutes_from_midnight: int
    duration_minutes: int
    week_type: str = "W"
    period_mask: int = 0
    timeslot_id: int = 0
    teacher_ids: List[int] = field(default_factory=list)
    division_ids: List[int] = field(default_factory=list)
    teacher_preferred_classroom_ids: List[int] = field(default_factory=list)
    division_preferred_classroom_ids: List[int] = field(default_factory=list)
    effective_headcount: Optional[int] = None
    candidate_classrooms: Annotated[List[PlanningClassroom], ValueRangeProvider(id='candidateClassroomsRange')] = field(default_factory=list)
    classroom: Annotated[Optional[PlanningClassroom], PlanningVariable(value_range_provider_refs=['candidateClassroomsRange'], allows_unassigned=True)] = None


@planning_solution
@dataclass
class PlanningRoomTimetable:
    classrooms: Annotated[List[PlanningClassroom], ProblemFactCollectionProperty] = field(default_factory=list)
    fixed_bookings: Annotated[List[PlanningFixedRoomBooking], ProblemFactCollectionProperty] = field(default_factory=list)
    preferences: Annotated[List[PlanningPreference], ProblemFactCollectionProperty] = field(default_factory=list)
    optimization_settings: Annotated[List[PlanningRoomOptimizationSettings], ProblemFactCollectionProperty] = field(default_factory=list)
    assignments: Annotated[List[PlanningRoomAssignment], PlanningEntityCollectionProperty] = field(default_factory=list)
    score: Annotated[HardSoftScore, PlanningScore] = None


def _rooms_overlap(day1, week1, period1, start1, dur1, day2, week2, period2, start2, dur2) -> bool:
    """Les 5 conditions de chevauchement (mêmes que leaf_classroom_conflict, constraints.py),
    factorisées ici en fonction nommée à args scalaires — pas de lambda générateur (voir la
    ClassCastException JPype rencontrée et corrigée dans constraints.py, même précaution)."""
    if day1 != day2:
        return False
    if not weeks_overlap(week1, week2):
        return False
    if not periods_overlap(period1, period2):
        return False
    return not _not_overlapping(start1, dur1, start2, dur2)


def _assignments_overlap(a1: PlanningRoomAssignment, a2: PlanningRoomAssignment) -> bool:
    return _rooms_overlap(
        a1.day_of_week, a1.week_type, a1.period_mask, a1.minutes_from_midnight, a1.duration_minutes,
        a2.day_of_week, a2.week_type, a2.period_mask, a2.minutes_from_midnight, a2.duration_minutes,
    )


def _assignment_overlaps_booking(a: PlanningRoomAssignment, b: PlanningFixedRoomBooking) -> bool:
    return _rooms_overlap(
        a.day_of_week, a.week_type, a.period_mask, a.minutes_from_midnight, a.duration_minutes,
        b.day_of_week, b.week_type, b.period_mask, b.minutes_from_midnight, b.duration_minutes,
    )


def room_conflict_between_assignments(constraint_factory: ConstraintFactory) -> Constraint:
    """
    Mêmes 5 conditions de chevauchement que leaf_classroom_conflict (constraints.py), SAUF
    hierarchy_overlap (pas de 4ᵉ condition ici) — différence volontaire et importante par rapport
    à COURSE_PLACEMENT : deux PlanningRoomAssignment d'une même fratrie (enfants d'un même cours
    composé) DOIVENT être traités en conflit normal s'ils demandent la même salle-feuille au même
    moment — c'est justement ce qui les force vers des salles distinctes. Reprendre
    hierarchy_overlap ici serait un bug direct (deux enfants pourraient recevoir la même salle).
    """
    return (
        constraint_factory.for_each_unique_pair(
            PlanningRoomAssignment,
            Joiners.equal(lambda a: a.classroom.id if a.classroom is not None else -1)
        )
        .filter(lambda a1, a2: a1.classroom is not None and a2.classroom is not None)
        .filter(_assignments_overlap)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Room conflict between assignments")
    )


def room_conflict_with_fixed_booking(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None)
        .join(
            PlanningFixedRoomBooking,
            Joiners.equal(lambda a: a.classroom.id, lambda b: b.classroom_id)
        )
        .filter(_assignment_overlaps_booking)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Room conflict with fixed booking")
    )


def room_capacity_hard(constraint_factory: ConstraintFactory) -> Constraint:
    """NULL de part et d'autre (capacité illimitée, ou effectif du cours inconnu) = pas de
    vérification — règle validée en amont de l'implémentation."""
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None
                and a.classroom.capacity is not None
                and a.effective_headcount is not None
                and a.effective_headcount > a.classroom.capacity)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Room capacity exceeded")
    )


def unassigned_room_assignment_penalty(constraint_factory: ConstraintFactory) -> Constraint:
    """Même philosophie que penalize_unassigned_course (COURSE_PLACEMENT, Overconstrained
    Planning) : une unité non résolue coûte le même prix qu'un conflit dur, pour que le solveur
    puisse transiter par des états intermédiaires plutôt que de rester bloqué."""
    return (
        constraint_factory.for_each_including_unassigned(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is None)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Unassigned room assignment")
    )


def room_preference_hard(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None)
        .join(
            PlanningPreference,
            Joiners.equal(lambda a: a.timeslot_id, lambda p: p.timeslot_id)
        )
        .filter(lambda a, p: p.resource_type == "Classroom" and p.preference_level == "Unsuited"
                and p.resource_id == a.classroom.id
                and weeks_overlap(a.week_type, p.week_type) and periods_overlap(a.period_mask, p.period_mask))
        # of_hard(1000), pas ONE_HARD : sinon strictement à égalité avec
        # unassigned_room_assignment_penalty (ONE_HARD lui aussi) — le solveur n'aurait alors
        # aucune préférence entre "assigner quand même une salle Unsuited" et "laisser
        # l'affectation non résolue", et pourrait très bien converger sur la première (un
        # hill-climbing ne fait pas de mouvement latéral à score égal, rien ne le pousse vers
        # l'option pourtant voulue). 1000 domine tout cumul réaliste d'affectations non résolues.
        .penalize(HardSoftScore.of_hard(1000))
        .as_constraint("Room preference unsuited")
    )


def room_preference_soft_penalty(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None)
        .join(
            PlanningPreference,
            Joiners.equal(lambda a: a.timeslot_id, lambda p: p.timeslot_id)
        )
        .filter(lambda a, p: p.resource_type == "Classroom" and p.preference_level == "Undesirable"
                and p.resource_id == a.classroom.id
                and weeks_overlap(a.week_type, p.week_type) and periods_overlap(a.period_mask, p.period_mask))
        .penalize(HardSoftScore.of_soft(10))
        .as_constraint("Room preference undesirable")
    )


def room_preference_soft_reward(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None)
        .join(
            PlanningPreference,
            Joiners.equal(lambda a: a.timeslot_id, lambda p: p.timeslot_id)
        )
        .filter(lambda a, p: p.resource_type == "Classroom" and p.preference_level == "Preferred"
                and p.resource_id == a.classroom.id
                and weeks_overlap(a.week_type, p.week_type) and periods_overlap(a.period_mask, p.period_mask))
        .reward(HardSoftScore.of_soft(10))
        .as_constraint("Room preference preferred")
    )


def teacher_preferred_classroom_reward(constraint_factory: ConstraintFactory) -> Constraint:
    """Continuité (§3.0) : récompense un professeur qui retrouve une de ses salles préférées."""
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None and a.classroom.id in a.teacher_preferred_classroom_ids)
        .reward(HardSoftScore.ONE_SOFT)
        .as_constraint("Teacher preferred classroom reward")
    )


def division_preferred_classroom_reward(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None and a.classroom.id in a.division_preferred_classroom_ids)
        .reward(HardSoftScore.ONE_SOFT)
        .as_constraint("Division preferred classroom reward")
    )


# ==========================================
# CONTINUITÉ DE SALLE (limiter les déplacements d'un professeur/d'une division)
# ==========================================
# "Cours consécutif" = le prochain cours RÉEL de ce jour pour cette personne, même s'il y a un
# trou (heure libre) entre les deux — pas seulement un enchaînement sans trou (choix utilisateur).

def _count_room_continuity_breaks(rows, id_field: str) -> int:
    """rows : PlanningRoomAssignment d'UN SEUL day_of_week, déjà filtrés classroom is not None.
    Explose par personne (teacher_ids ou division_ids), trie par heure de début, ne compare que
    les VRAIS voisins consécutifs — pas toutes les paires. Fonction Python pure appelée depuis un
    ConstraintCollectors.to_list() : jamais de generator expression/bool() sur liste dans un lambda
    passé à Timefold, jpyinterpreter a déjà planté sur ces deux formes cette session."""
    from collections import defaultdict
    by_person = defaultdict(list)
    for a in rows:
        for pid in getattr(a, id_field):
            by_person[pid].append(a)

    breaks = 0
    for courses in by_person.values():
        courses.sort(key=lambda a: (a.minutes_from_midnight, a.id))
        for i, cur in enumerate(courses):
            cur_end = _end_minutes(cur.minutes_from_midnight, cur.duration_minutes)
            for nxt in courses[i + 1:]:
                # Exclut les vraies simultanéités (siblings quantity>1, forcés vers des salles
                # différentes par room_conflict_between_assignments) : ce n'est pas un déplacement,
                # on ignore et on continue à chercher le vrai voisin suivant.
                if nxt.minutes_from_midnight < cur_end:
                    continue
                if weeks_overlap(cur.week_type, nxt.week_type) and periods_overlap(cur.period_mask, nxt.period_mask):
                    if cur.classroom.id != nxt.classroom.id:
                        breaks += 1
                    break
    return breaks


def teacher_room_continuity_penalty(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None)
        .group_by(lambda a: a.day_of_week, ConstraintCollectors.to_list())
        .join(PlanningRoomOptimizationSettings)
        .filter(lambda day, rows, settings: _count_room_continuity_breaks(rows, 'teacher_ids') > 0)
        .penalize(HardSoftScore.ONE_SOFT, lambda day, rows, settings:
                  _count_room_continuity_breaks(rows, 'teacher_ids') * (10 if settings.optimize_target == "TEACHER" else 1))
        .as_constraint("Teacher room continuity")
    )


def division_room_continuity_penalty(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None)
        .group_by(lambda a: a.day_of_week, ConstraintCollectors.to_list())
        .join(PlanningRoomOptimizationSettings)
        .filter(lambda day, rows, settings: _count_room_continuity_breaks(rows, 'division_ids') > 0)
        .penalize(HardSoftScore.ONE_SOFT, lambda day, rows, settings:
                  _count_room_continuity_breaks(rows, 'division_ids') * (10 if settings.optimize_target == "DIVISION" else 1))
        .as_constraint("Division room continuity")
    )


def _shares_person(ids_a: List[int], ids_b: List[int]) -> bool:
    for pid in ids_a:
        if pid in ids_b:
            return True
    return False


def _end_minutes(start: int, duration: int) -> int:
    return start + duration


def _not_overlapping(a_start: int, a_dur: int, b_start: int, b_dur: int) -> bool:
    return a_start >= _end_minutes(b_start, b_dur) or b_start >= _end_minutes(a_start, a_dur)


def _pair_bounds(a_start: int, a_dur: int, b_start: int, b_dur: int):
    """Bornes ordonnées (fin du plus tôt, début du plus tard) de la paire, quel que soit l'ordre
    d'origine — a et b peuvent être dans n'importe quel ordre chronologique."""
    if a_start <= b_start:
        return _end_minutes(a_start, a_dur), b_start
    return _end_minutes(b_start, b_dur), a_start


def _teacher_pair_same_day_not_overlapping(a: PlanningRoomAssignment, b: PlanningFixedRoomBooking) -> bool:
    if not _shares_person(a.teacher_ids, b.teacher_ids):
        return False
    if not weeks_overlap(a.week_type, b.week_type) or not periods_overlap(a.period_mask, b.period_mask):
        return False
    # Exclut le chevauchement temporel (co-enseignement/quantity>1 simultané), même raison que
    # _count_room_continuity_breaks : ce n'est pas un déplacement.
    return _not_overlapping(a.minutes_from_midnight, a.duration_minutes, b.minutes_from_midnight, b.duration_minutes)


def _pair_different_room(a: PlanningRoomAssignment, b: PlanningFixedRoomBooking) -> bool:
    return a.classroom.id != b.classroom_id


def _other_assignment_between_teacher(a: PlanningRoomAssignment, b: PlanningFixedRoomBooking, other: PlanningRoomAssignment) -> bool:
    if other.classroom is None or other.id == a.id:
        return False
    if not (_shares_person(other.teacher_ids, a.teacher_ids) or _shares_person(other.teacher_ids, b.teacher_ids)):
        return False
    if other.day_of_week != a.day_of_week:
        return False
    if not weeks_overlap(other.week_type, a.week_type) or not periods_overlap(other.period_mask, a.period_mask):
        return False
    earlier_end, later_start = _pair_bounds(a.minutes_from_midnight, a.duration_minutes, b.minutes_from_midnight, b.duration_minutes)
    return earlier_end <= other.minutes_from_midnight < later_start


def _other_booking_between_teacher(a: PlanningRoomAssignment, b: PlanningFixedRoomBooking, other: PlanningFixedRoomBooking) -> bool:
    if not (_shares_person(other.teacher_ids, a.teacher_ids) or _shares_person(other.teacher_ids, b.teacher_ids)):
        return False
    if other.day_of_week != a.day_of_week:
        return False
    if not weeks_overlap(other.week_type, a.week_type) or not periods_overlap(other.period_mask, a.period_mask):
        return False
    earlier_end, later_start = _pair_bounds(a.minutes_from_midnight, a.duration_minutes, b.minutes_from_midnight, b.duration_minutes)
    return earlier_end <= other.minutes_from_midnight < later_start


def _division_pair_same_day_not_overlapping(a: PlanningRoomAssignment, b: PlanningFixedRoomBooking) -> bool:
    if not _shares_person(a.division_ids, b.division_ids):
        return False
    if not weeks_overlap(a.week_type, b.week_type) or not periods_overlap(a.period_mask, b.period_mask):
        return False
    return _not_overlapping(a.minutes_from_midnight, a.duration_minutes, b.minutes_from_midnight, b.duration_minutes)


def _other_assignment_between_division(a: PlanningRoomAssignment, b: PlanningFixedRoomBooking, other: PlanningRoomAssignment) -> bool:
    if other.classroom is None or other.id == a.id:
        return False
    if not (_shares_person(other.division_ids, a.division_ids) or _shares_person(other.division_ids, b.division_ids)):
        return False
    if other.day_of_week != a.day_of_week:
        return False
    if not weeks_overlap(other.week_type, a.week_type) or not periods_overlap(other.period_mask, a.period_mask):
        return False
    earlier_end, later_start = _pair_bounds(a.minutes_from_midnight, a.duration_minutes, b.minutes_from_midnight, b.duration_minutes)
    return earlier_end <= other.minutes_from_midnight < later_start


def _other_booking_between_division(a: PlanningRoomAssignment, b: PlanningFixedRoomBooking, other: PlanningFixedRoomBooking) -> bool:
    if not (_shares_person(other.division_ids, a.division_ids) or _shares_person(other.division_ids, b.division_ids)):
        return False
    if other.day_of_week != a.day_of_week:
        return False
    if not weeks_overlap(other.week_type, a.week_type) or not periods_overlap(other.period_mask, a.period_mask):
        return False
    earlier_end, later_start = _pair_bounds(a.minutes_from_midnight, a.duration_minutes, b.minutes_from_midnight, b.duration_minutes)
    return earlier_end <= other.minutes_from_midnight < later_start


def teacher_room_continuity_with_fixed_booking(constraint_factory: ConstraintFactory) -> Constraint:
    """
    Repli Phase 2 : une PlanningFixedRoomBooking (salle déjà figée) n'est pas un
    PlanningRoomAssignment, donc pas de group_by commun possible avec _count_room_continuity_breaks
    — confirmé via lecture directe du SDK Timefold 1.24.0b0 (_constraint_stream.py) que join() ne
    prend jamais un flux déjà group_by-é comme second membre. Repli : comparaison par paire avec
    deux anti-jointures if_not_exists (pattern déjà utilisé par
    constraints.py::subject_default_incompatible_same_day) pour vérifier qu'aucun AUTRE cours ne
    s'intercale.

    Limite assumée : "partage un professeur" matche sur "partage AU MOINS UN professeur", pas sur
    l'identité précise de la personne dont la chaîne est rompue — un cours co-enseigné par deux
    professeurs différents de ceux de la réservation fixe pourrait être imprécisément apparié.
    Limite étroite (cas de co-enseignement à effectifs partiellement différents uniquement),
    largement préférable à l'absence de vérification d'adjacence réelle contre les salles figées.
    """
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None)
        .join(PlanningFixedRoomBooking, Joiners.equal(lambda a: a.day_of_week, lambda b: b.day_of_week))
        .filter(_teacher_pair_same_day_not_overlapping)
        .filter(_pair_different_room)
        .if_not_exists(PlanningRoomAssignment, Joiners.filtering(_other_assignment_between_teacher))
        .if_not_exists(PlanningFixedRoomBooking, Joiners.filtering(_other_booking_between_teacher))
        .join(PlanningRoomOptimizationSettings)
        .penalize(HardSoftScore.ONE_SOFT, lambda a, b, settings: 10 if settings.optimize_target == "TEACHER" else 1)
        .as_constraint("Teacher room continuity with fixed booking")
    )


def division_room_continuity_with_fixed_booking(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningRoomAssignment)
        .filter(lambda a: a.classroom is not None)
        .join(PlanningFixedRoomBooking, Joiners.equal(lambda a: a.day_of_week, lambda b: b.day_of_week))
        .filter(_division_pair_same_day_not_overlapping)
        .filter(_pair_different_room)
        .if_not_exists(PlanningRoomAssignment, Joiners.filtering(_other_assignment_between_division))
        .if_not_exists(PlanningFixedRoomBooking, Joiners.filtering(_other_booking_between_division))
        .join(PlanningRoomOptimizationSettings)
        .penalize(HardSoftScore.ONE_SOFT, lambda a, b, settings: 10 if settings.optimize_target == "DIVISION" else 1)
        .as_constraint("Division room continuity with fixed booking")
    )


@constraint_provider
def define_room_constraints(constraint_factory: ConstraintFactory) -> list[Constraint]:
    return [
        unassigned_room_assignment_penalty(constraint_factory),
        room_conflict_between_assignments(constraint_factory),
        room_conflict_with_fixed_booking(constraint_factory),
        room_capacity_hard(constraint_factory),
        room_preference_hard(constraint_factory),
        room_preference_soft_penalty(constraint_factory),
        room_preference_soft_reward(constraint_factory),
        teacher_preferred_classroom_reward(constraint_factory),
        division_preferred_classroom_reward(constraint_factory),
        teacher_room_continuity_penalty(constraint_factory),
        division_room_continuity_penalty(constraint_factory),
        teacher_room_continuity_with_fixed_booking(constraint_factory),
        division_room_continuity_with_fixed_booking(constraint_factory),
    ]

"""
Affectation automatique des besoins aux professeurs (Service non verrouillé -> Teacher qualifié).

Algorithme classique, PAS Timefold (voir specs/002-yearly-timetabling-core/
teacher-assignment-proposal.md §0 pour l'argumentaire complet) : formulé comme un flot à coût
minimal à deux paliers de capacité par professeur (networkx). Ce choix garantit PAR CONSTRUCTION
la minimisation globale des HSA de l'établissement (§2 de la proposition) — un glouton par ordre
de priorité ne le garantit pas (un premier besoin peut accaparer le seul professeur disponible en
palier normal et forcer un besoin suivant, de la même discipline, à tomber en HSA évitable).

Ne modifie JAMAIS la base directement : ce module ne fait que calculer une proposition
(compute_assignment_proposal). L'écriture réelle dans Service.teachers appartient à
wizard_teacher_assignment.py::rpc_apply.
"""
from dataclasses import dataclass, field
from typing import Optional
import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.service import Service
from backend.app.models.teacher import Teacher, TeacherDiscipline, teacher_incompatibilities
from backend.app.models.teacher_grade_preference import TeacherGradePreference
from backend.app.models.preference import ResourcePreference, PreferenceLevel
from backend.app.models.timeslot import Timeslot

# Coûts entiers (networkx exige des poids entiers pour min_cost_flow) : les trois paliers sont
# volontairement séparés par plusieurs ordres de grandeur, pour que le flot sature TOUJOURS un
# palier moins cher avant de toucher le suivant — quels que soient les coûts de priorité/
# compatibilité horaire À L'INTÉRIEUR d'un même palier (voir teacher-assignment-proposal.md §2).
TIER1_BASE_COST = 1
HSA_TIER_COST = 100_000
UNMET_TIER_COST = 100_000_000
PRIORITY_WEIGHT = 10       # priorité TeacherGradePreference 1..5 -> contribution 10..50
COMPATIBILITY_WEIGHT = 5   # pénalité horaire, proportionnelle au %age de créneaux bloqués en commun

# Nombre maximum de re-résolutions tentées par conflit lors des passes de réparation (§5.3) — un
# garde-fou de performance, pas une limite fonctionnelle attendue en usage normal (le nombre de
# conflits réels sur un établissement reste faible, voir teacher-assignment-proposal.md §5.3).
MAX_REPAIR_ATTEMPTS_PER_CONFLICT = 2


@dataclass
class Warning_:
    type: str
    message: str
    service_ids: list = field(default_factory=list)
    teacher_ids: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
#   Capacité (voir teacher-assignment-proposal.md §5.2)                       #
# --------------------------------------------------------------------------- #

def _teacher_capacity_by_discipline(db: Session, teacher: Teacher, discipline_id: int) -> int:
    """
    assignable_capacity(T, D) — calculée sous db.filter_discipline_id (même contexte ambiant que
    trmd_synthesis.py, voir teacher.py) pour que discipline_duration_minutes/ara_duration_minutes/
    are_duration_minutes/other_school_duration_minutes ne portent que sur CETTE discipline (ARA/
    ARE/CSD sont attribuées à la discipline majeure du professeur par ce même mécanisme, aucun
    code spécifique nécessaire ici).
    """
    previous = getattr(db, "filter_discipline_id", None)
    db.filter_discipline_id = discipline_id
    try:
        return (
            teacher.discipline_duration_minutes
            - teacher.ara_duration_minutes
            + teacher.are_duration_minutes
            - teacher.other_school_duration_minutes
        )
    finally:
        db.filter_discipline_id = previous


def _qualified_teachers(db: Session, discipline_id: int) -> list:
    teacher_ids = [
        row[0] for row in db.query(TeacherDiscipline.teacher_id)
        .filter(TeacherDiscipline.discipline_id == discipline_id).distinct().all()
    ]
    if not teacher_ids:
        return []
    return db.query(Teacher).filter(Teacher.id.in_(teacher_ids)).all()


def _division_id_for_service(service: Service) -> Optional[int]:
    """
    Résout la Division réelle d'un Service, qu'il soit lié directement (MefDivision, via le
    related_field division_id déjà présent sur Service) ou via un Group — dans ce second cas, les
    ClassPart d'un même Group appartiennent toutes à la même Division (voir group.py), donc
    n'importe laquelle suffit à résoudre la division commune.
    """
    if service.division_id:
        return service.division_id
    if service.group and service.group.class_parts:
        return service.group.class_parts[0].division_id
    return None


def _service_need_minutes(service: Service) -> int:
    return sum(r.weighted_need_weekly_duration_minutes for r in service.repartitions)


def _eligible_services(db: Session) -> list:
    """Service non verrouillés (teachers_locked=False, voir §4.5) avec un besoin non nul."""
    services = db.query(Service).filter(Service.teachers_locked.is_(False)).all()
    return [s for s in services if _service_need_minutes(s) > 0]


# --------------------------------------------------------------------------- #
#   Coût pairwise (priorité de niveau + compatibilité horaire, voir §0/§5.2)   #
# --------------------------------------------------------------------------- #

def _teacher_grade_preference(db: Session, teacher_id: int, ref_grade_id: Optional[int]):
    if ref_grade_id is None:
        return None
    return db.query(TeacherGradePreference).filter(
        TeacherGradePreference.teacher_id == teacher_id,
        TeacherGradePreference.ref_grade_id == ref_grade_id,
    ).first()


def _priority_for(db: Session, teacher_id: int, ref_grade_id: Optional[int]) -> int:
    """
    1 (à affecter en priorité) .. 5 (en dernier). Défaut neutre 3 si la ligne
    TeacherGradePreference est absente — ne devrait arriver qu'avec des données insérées en SQL
    brut hors cascade Teacher.create()/RefGrade.create() (voir seed).
    """
    pref = _teacher_grade_preference(db, teacher_id, ref_grade_id)
    return pref.priority if pref else 3


def _unsuited_timeslot_ids(db: Session, resource_type: str, resource_id: int) -> set:
    rows = db.query(ResourcePreference.timeslot_id).filter(
        ResourcePreference.resource_type == resource_type,
        ResourcePreference.resource_id == resource_id,
        ResourcePreference.preference_level == PreferenceLevel.UNSUITED,
    ).all()
    return {r[0] for r in rows}


def _compatibility_penalty(db: Session, teacher_id: int, division_id: Optional[int], total_timeslot_count: int) -> int:
    """
    Signal de compatibilité horaire pairwise (voir teacher-assignment-proposal.md §0) : proportion
    de créneaux bloqués (Unsuited) EN COMMUN entre le professeur et la division, rapportée au
    nombre total de créneaux de la grille — PAS une garantie de faisabilité (rôle réservé à
    COURSE_PLACEMENT en aval, voir §0 "hors périmètre assumé"), juste un coût d'arête qui
    défavorise les paires structurellement les plus contraintes des deux côtés à la fois (exemple :
    un professeur disponible seulement mardi/mercredi pour une division fermée le mercredi).
    """
    if not division_id or not total_timeslot_count:
        return 0
    teacher_blocked = _unsuited_timeslot_ids(db, "Teacher", teacher_id)
    if not teacher_blocked:
        return 0
    division_blocked = _unsuited_timeslot_ids(db, "Division", division_id)
    overlap = len(teacher_blocked & division_blocked)
    return round(COMPATIBILITY_WEIGHT * 100 * overlap / total_timeslot_count)


def _pairwise_cost(db: Session, teacher: Teacher, service: Service, total_timeslot_count: int) -> int:
    priority = _priority_for(db, teacher.id, service.ref_grade_id)
    penalty = _compatibility_penalty(db, teacher.id, _division_id_for_service(service), total_timeslot_count)
    return priority * PRIORITY_WEIGHT + penalty


# --------------------------------------------------------------------------- #
#   Incompatibilités (voir §4.4)                                              #
# --------------------------------------------------------------------------- #

def _are_incompatible(db: Session, teacher_id_a: int, teacher_id_b: int) -> bool:
    """
    Une seule direction à vérifier : teacher_incompatibilities est maintenue symétrique par
    Teacher._mirror_incompatibilities (voir teacher.py) — si A est incompatible avec B, la ligne
    inverse existe forcément aussi, mais l'inverse suffit déjà à répondre.
    """
    row = db.execute(
        select(teacher_incompatibilities.c.teacher_id).where(
            teacher_incompatibilities.c.teacher_id == teacher_id_a,
            teacher_incompatibilities.c.incompatible_teacher_id == teacher_id_b,
        )
    ).first()
    return row is not None


# --------------------------------------------------------------------------- #
#   Construction du graphe de flot                                            #
# --------------------------------------------------------------------------- #

def _teacher_sink(G: nx.DiGraph, teacher_sink_of: dict, teacher_id: int) -> str:
    node = teacher_sink_of.get(teacher_id)
    if node is None:
        node = f"teacher:{teacher_id}"
        teacher_sink_of[teacher_id] = node
        G.add_node(node, demand=0)
    return node


def _hsa_pool(G: nx.DiGraph, hsa_pool_of: dict, teacher_sink_of: dict, teacher: Teacher) -> str:
    """
    Un seul nœud HSA par professeur, PARTAGÉ entre toutes ses disciplines (voir §5.1) : le
    débordement de chaque palier 1 discipline y converge, plafonné une seule fois par
    max_hsa_duration_minutes — cohérent avec le fait que ce soit une enveloppe administrative
    globale au professeur, pas déclinée par discipline.
    """
    node = hsa_pool_of.get(teacher.id)
    if node is None:
        node = f"hsa:{teacher.id}"
        hsa_pool_of[teacher.id] = node
        G.add_node(node, demand=0)
        G.add_edge(node, _teacher_sink(G, teacher_sink_of, teacher.id), capacity=teacher.max_hsa_duration_minutes, weight=0)
    return node


def _build_graph(db: Session, services: list, forbidden_edges: frozenset = frozenset()):
    """
    forbidden_edges : ensemble de (service_id, teacher_id) à exclure du graphe — utilisé par les
    passes de réparation (voir _repair) pour relancer une résolution contrainte sans réécrire tout
    le graphe à la main (voir §5.3 : "interdire temporairement l'arête ... et relancer la
    résolution complète").

    Chaque Service reçoit systématiquement un arc de secours vers un puits "unmet" (coût
    UNMET_TIER_COST, le plus cher des trois paliers) : le flot reste TOUJOURS faisable même quand
    aucun professeur qualifié n'a de capacité disponible, un besoin non couvert devient alors un
    simple avertissement plutôt qu'une exception NetworkXUnfeasible.

    Retourne (graph, need_node_of, tier1_teacher_of, hsa_teacher_of, unmet_node_of).
    """
    total_timeslot_count = db.query(Timeslot).count()

    G = nx.DiGraph()
    G.add_node("SOURCE", demand=0)
    G.add_node("SINK", demand=0)

    total_need = 0
    need_node_of = {}
    unmet_node_of = {}
    tier1_node_of = {}       # (teacher_id, discipline_id) -> node
    tier1_teacher_of = {}    # node -> (teacher_id, discipline_id)
    hsa_pool_of = {}         # teacher_id -> node
    hsa_teacher_of = {}      # node -> teacher_id
    teacher_sink_of = {}     # teacher_id -> node

    for service in services:
        need = _service_need_minutes(service)
        total_need += need
        need_node = f"need:{service.id}"
        need_node_of[service.id] = need_node
        G.add_node(need_node, demand=0)
        G.add_edge("SOURCE", need_node, capacity=need, weight=0)

        unmet_node = f"unmet:{service.id}"
        unmet_node_of[service.id] = unmet_node
        G.add_node(unmet_node, demand=0)
        G.add_edge(need_node, unmet_node, capacity=need, weight=UNMET_TIER_COST)
        G.add_edge(unmet_node, "SINK", capacity=need, weight=0)

        for teacher in _qualified_teachers(db, service.discipline_id):
            if (service.id, teacher.id) in forbidden_edges:
                continue

            tier1_key = (teacher.id, service.discipline_id)
            tier1_node = tier1_node_of.get(tier1_key)
            if tier1_node is None:
                tier1_node = f"tier1:{teacher.id}:{service.discipline_id}"
                tier1_node_of[tier1_key] = tier1_node
                tier1_teacher_of[tier1_node] = tier1_key
                capacity = max(0, _teacher_capacity_by_discipline(db, teacher, service.discipline_id))
                G.add_node(tier1_node, demand=0)
                G.add_edge(tier1_node, _teacher_sink(G, teacher_sink_of, teacher.id), capacity=capacity, weight=0)

            hsa_node = _hsa_pool(G, hsa_pool_of, teacher_sink_of, teacher)
            hsa_teacher_of[hsa_node] = teacher.id

            cost = _pairwise_cost(db, teacher, service, total_timeslot_count)
            G.add_edge(need_node, tier1_node, capacity=need, weight=TIER1_BASE_COST + cost)
            G.add_edge(need_node, hsa_node, capacity=need, weight=HSA_TIER_COST + cost)

    for teacher_id, sink_node in teacher_sink_of.items():
        G.add_edge(sink_node, "SINK", capacity=total_need, weight=0)

    G.nodes["SOURCE"]["demand"] = -total_need
    G.nodes["SINK"]["demand"] = total_need

    return G, need_node_of, tier1_teacher_of, hsa_teacher_of, unmet_node_of


# --------------------------------------------------------------------------- #
#   Résolution et extraction                                                  #
# --------------------------------------------------------------------------- #

def _solve_and_extract(db: Session, services: list, forbidden_edges: frozenset = frozenset()):
    """
    Résout le flot et reconstruit, par Service, la liste des professeurs qui ont reçu au moins une
    unité de flot (co-enseignement/partage naturellement représentés : plusieurs professeurs
    peuvent recevoir du flot pour le même besoin). Retourne (assignments, warnings) où assignments
    est {service_id: {"teacher_ids": [...], "tier": "normal"|"hsa"|"mixed"}}.
    """
    if not services:
        return {}, []

    G, need_node_of, tier1_teacher_of, hsa_teacher_of, unmet_node_of = _build_graph(db, services, forbidden_edges)
    flow_dict = nx.min_cost_flow(G)

    assignments = {s.id: {"teacher_ids": [], "tier": None} for s in services}
    warnings = []

    for service in services:
        need_node = need_node_of[service.id]
        flows = flow_dict.get(need_node, {})
        tiers_used = set()
        for target_node, amount in flows.items():
            if amount <= 0:
                continue
            if target_node in tier1_teacher_of:
                teacher_id, _discipline_id = tier1_teacher_of[target_node]
                assignments[service.id]["teacher_ids"].append(teacher_id)
                tiers_used.add("normal")
            elif target_node in hsa_teacher_of:
                teacher_id = hsa_teacher_of[target_node]
                if teacher_id not in assignments[service.id]["teacher_ids"]:
                    assignments[service.id]["teacher_ids"].append(teacher_id)
                tiers_used.add("hsa")
            elif target_node == unmet_node_of.get(service.id):
                warnings.append(Warning_(
                    type="unmet_need",
                    message=f"Besoin non couvert pour le service #{service.id} ({amount} min. sans professeur).",
                    service_ids=[service.id],
                ))
        assignments[service.id]["tier"] = "mixed" if len(tiers_used) > 1 else (next(iter(tiers_used), None))

    return assignments, warnings


# --------------------------------------------------------------------------- #
#   Réparation par re-résolution contrainte (voir §5.3)                       #
# --------------------------------------------------------------------------- #

def _conflicting_division_pairs(db: Session, services_by_id: dict, assignments: dict):
    """
    Balaie toutes les divisions occupées par les propositions courantes et retourne la liste des
    conflits trouvés, sous la forme (service_id_a, teacher_id_a, service_id_b, teacher_id_b).
    """
    by_division = {}
    for service_id, result in assignments.items():
        division_id = _division_id_for_service(services_by_id[service_id])
        if not division_id:
            continue
        for teacher_id in result["teacher_ids"]:
            by_division.setdefault(division_id, []).append((service_id, teacher_id))

    conflicts = []
    for entries in by_division.values():
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                s_a, t_a = entries[i]
                s_b, t_b = entries[j]
                if t_a == t_b:
                    continue
                if _are_incompatible(db, t_a, t_b):
                    conflicts.append((s_a, t_a, s_b, t_b))
    return conflicts


def _repair_incompatibilities(db: Session, services: list, assignments: dict, unmet_warnings: list, structural_warnings: list):
    """
    Pour chaque conflit détecté (deux professeurs incompatibles coaffectés sur la même division,
    voir §4.4) : interdit l'arête (service_a, teacher_a) et relance une résolution COMPLÈTE du
    flot ; si le conflit persiste, tente l'inverse (service_b, teacher_b). Seulement si les deux
    tentatives échouent, le conflit est laissé tel quel et surfacé en avertissement — voir §5.3,
    c'est la seule situation où l'utilisateur est sollicité pour ce type de problème (certitude
    garantie par l'optimalité du flot, pas une estimation).

    `unmet_warnings` est remplacée EN BLOC à chaque réparation réussie (pas fusionnée) : les
    avertissements "besoin non couvert" d'une résolution intermédiaire abandonnée n'ont plus de
    sens une fois `assignments` remplacé par le résultat de la résolution suivante.
    `structural_warnings` accumule uniquement les "incompatibility_unresolved" de CETTE passe.

    Retourne (assignments, unmet_warnings, structural_warnings).
    """
    services_by_id = {s.id: s for s in services}
    forbidden_edges = set()
    attempts = 0

    while attempts < MAX_REPAIR_ATTEMPTS_PER_CONFLICT * len(services) + 20:
        conflicts = _conflicting_division_pairs(db, services_by_id, assignments)
        if not conflicts:
            break
        s_a, t_a, s_b, t_b = conflicts[0]
        attempts += 1

        resolved = False
        for candidate_edge in [(s_a, t_a), (s_b, t_b)]:
            trial_forbidden = forbidden_edges | {candidate_edge}
            trial_assignments, trial_unmet_warnings = _solve_and_extract(db, services, frozenset(trial_forbidden))
            # Une "résolution" qui laisse le service du professeur interdit sans AUCUN professeur
            # n'en est pas une : _conflicting_division_pairs ne verrait plus de conflit (il faut
            # être deux pour se disputer une division), mais on aurait juste transformé
            # silencieusement l'incompatibilité en besoin non couvert — pas un vrai remplaçant.
            forbidden_service_id, _forbidden_teacher_id = candidate_edge
            genuinely_replaced = bool(trial_assignments[forbidden_service_id]["teacher_ids"])
            if genuinely_replaced and not _conflicting_division_pairs(db, services_by_id, trial_assignments):
                forbidden_edges = trial_forbidden
                assignments = trial_assignments
                unmet_warnings = trial_unmet_warnings
                resolved = True
                break

        if not resolved:
            division_id = _division_id_for_service(services_by_id[s_a])
            structural_warnings.append(Warning_(
                type="incompatibility_unresolved",
                message=(
                    f"Incompatibilité non résolue sur la division #{division_id} : aucune "
                    f"réaffectation possible (certitude vérifiée par re-résolution du flot dans "
                    f"les deux sens) — professeurs #{t_a} et #{t_b}."
                ),
                service_ids=[s_a, s_b],
                teacher_ids=[t_a, t_b],
            ))
            # Le conflit reste dans `assignments` (proposition inchangée) : on sort après ce seul
            # signalement plutôt que de reboucler indéfiniment sur un conflit non réparable —
            # d'éventuels AUTRES conflits, sur d'autres divisions, restent non traités par cet
            # appel (acceptable : le pire cas reste un avertissement de moins affiché en une
            # passe, jamais une donnée incorrecte, et un nouvel appel à compute_assignment_proposal
            # après ajustement des critères repart d'un état propre).
            break

    return assignments, unmet_warnings, structural_warnings


def _grade_id_of(services_by_id: dict, service_id: int) -> Optional[int]:
    return services_by_id[service_id].ref_grade_id


def _max_class_count_violations(db: Session, services_by_id: dict, assignments: dict):
    """
    Pour chaque (professeur, niveau), compte le nombre de DIVISIONS DISTINCTES sur lesquelles il
    est proposé — si TeacherGradePreference.max_class_count est dépassé, retourne les couples
    (service_id, teacher_id) en excès (les plus récents dans l'itération, ordre arbitraire faute
    de critère de priorité par service, voir §3 de la proposition).
    """
    by_teacher_grade = {}
    for service_id, result in assignments.items():
        grade_id = _grade_id_of(services_by_id, service_id)
        division_id = _division_id_for_service(services_by_id[service_id])
        if grade_id is None or division_id is None:
            continue
        for teacher_id in result["teacher_ids"]:
            key = (teacher_id, grade_id)
            by_teacher_grade.setdefault(key, {}).setdefault(division_id, []).append(service_id)

    violations = []
    for (teacher_id, grade_id), divisions in by_teacher_grade.items():
        pref = _teacher_grade_preference(db, teacher_id, grade_id)
        if not pref or pref.max_class_count is None:
            continue
        if len(divisions) > pref.max_class_count:
            excess_divisions = list(divisions.items())[pref.max_class_count:]
            for _division_id, service_ids in excess_divisions:
                for service_id in service_ids:
                    violations.append((service_id, teacher_id))
    return violations


def _repair_max_class_count(db: Session, services: list, assignments: dict, unmet_warnings: list, structural_warnings: list):
    """Même mécanique de réparation que _repair_incompatibilities (re-résolution contrainte, voir
    sa docstring pour le traitement de unmet_warnings/structural_warnings), appliquée au
    dépassement de TeacherGradePreference.max_class_count plutôt qu'à une incompatibilité entre
    deux professeurs."""
    services_by_id = {s.id: s for s in services}
    forbidden_edges = set()
    attempts = 0

    while attempts < MAX_REPAIR_ATTEMPTS_PER_CONFLICT * len(services) + 20:
        violations = _max_class_count_violations(db, services_by_id, assignments)
        if not violations:
            break
        service_id, teacher_id = violations[0]
        attempts += 1

        trial_forbidden = forbidden_edges | {(service_id, teacher_id)}
        trial_assignments, trial_unmet_warnings = _solve_and_extract(db, services, frozenset(trial_forbidden))
        if len(_max_class_count_violations(db, services_by_id, trial_assignments)) < len(violations):
            forbidden_edges = trial_forbidden
            assignments = trial_assignments
            unmet_warnings = trial_unmet_warnings
            continue

        grade_id = _grade_id_of(services_by_id, service_id)
        structural_warnings.append(Warning_(
            type="max_class_count_unresolved",
            message=(
                f"Plafond de classes dépassé pour le professeur #{teacher_id} sur le niveau "
                f"#{grade_id} : aucune réaffectation ne permet de rester dans la limite déclarée."
            ),
            service_ids=[service_id],
            teacher_ids=[teacher_id],
        ))
        break

    return assignments, unmet_warnings, structural_warnings


# --------------------------------------------------------------------------- #
#   Point d'entrée                                                            #
# --------------------------------------------------------------------------- #

def compute_assignment_proposal(db: Session) -> dict:
    """
    Point d'entrée principal (voir wizard_teacher_assignment.py::rpc_simulate). Ne modifie RIEN en
    base — purement un calcul, à consommer tel quel par rpc_apply. Retourne :
      {"proposals": [{"service_id", "teacher_ids", "tier"}], "warnings": [{"type", "message", ...}]}
    """
    services = _eligible_services(db)
    if not services:
        return {"proposals": [], "warnings": []}

    assignments, unmet_warnings = _solve_and_extract(db, services)
    structural_warnings = []
    assignments, unmet_warnings, structural_warnings = _repair_incompatibilities(
        db, services, assignments, unmet_warnings, structural_warnings
    )
    assignments, unmet_warnings, structural_warnings = _repair_max_class_count(
        db, services, assignments, unmet_warnings, structural_warnings
    )

    proposals = [
        {"service_id": service_id, "teacher_ids": result["teacher_ids"], "tier": result["tier"]}
        for service_id, result in assignments.items()
        if result["teacher_ids"]
    ]
    return {
        "proposals": proposals,
        "warnings": [w.__dict__ for w in (unmet_warnings + structural_warnings)],
    }

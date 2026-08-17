from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from timefold.solver import SolverFactory
from timefold.solver.config import SolverConfig, SolverConfigOverride, TerminationConfig, ScoreDirectorFactoryConfig, Duration, EnvironmentMode, TerminationCompositionStyle
from timefold.solver import SolutionManager
from backend.app.core.config import settings
from backend.app.models.teacher import Teacher
from backend.app.models.non_teaching_staff import NonTeachingStaff
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.models.course_classroom_requirement import CourseClassroomRequirement
from backend.app.models.group import ClassPartLink
from backend.app.models.preference import ResourcePreference
from backend.app.models.constraint import ResourceConstraint, CourseToCourseConstraint, SubjectToSubjectConstraint
from backend.app.models.period import Period
from backend.app.core.database import SessionLocal, DEFAULT_DB_NAME
from backend.app.core import db_registry
from backend.app.core.exclusive_mode import enter_exclusive_mode, exit_exclusive_mode_and_rotate_token, clear_exclusive_mode
import logging
import threading
import time

logger = logging.getLogger(__name__)
from backend.app.solver.constraints import (
    PlanningTeacher,
    PlanningNonTeachingStaff,
    PlanningDivision,
    PlanningTimeslot,
    PlanningCourse,
    PlanningClassPartLink,
    PlanningPreference,
    PlanningResourceConstraint,
    PlanningCourseToCourseConstraint,
    PlanningGroupDemand,
    PlanningTimetable,
    define_constraints,
)


class _PerDbSolverState:
    """État d'une résolution en cours (ou en file d'attente) pour UNE base — voir SolverState."""
    __slots__ = (
        "lock", "active_solver", "status", "progress", "last_progress_at", "started_at", "time_limit_seconds",
        # Voir plan salles §4 : `kind` distingue les 4 points d'entrée (COURSE_PLACEMENT,
        # CLASSROOM_ASSIGNMENT, OPTIMIZE_COURSE_PLACEMENT, OPTIMIZE_CLASSROOM_ASSIGNMENT) — un seul
        # job actif par base quel que soit son kind (pas de champ séparé par type). pipeline_step/
        # pipeline_total_steps : 1/1 pour un solve simple, 1 ou 2 sur 2 pour le pipeline
        # d'optimisation (endpoint /optimize). stop_requested : positionné par stop_solving(),
        # consulté par l'orchestrateur du pipeline ENTRE deux phases (pas seulement pendant
        # solver.solve()) — voir le cas limite documenté dans _run_job.
        "kind", "pipeline_step", "pipeline_total_steps", "stop_requested",
    )

    def __init__(self):
        self.lock = threading.Lock()
        self.active_solver = None
        self.status = "NOT_SOLVING"
        self.progress = None
        self.last_progress_at = None
        self.started_at = None
        self.time_limit_seconds = None
        self.kind = None
        self.pipeline_step = 1
        self.pipeline_total_steps = 1
        self.stop_requested = False


# Sémaphore GLOBAL (toutes bases confondues), pas par base — voir architecture.md, "Concurrence des
# résolutions" : chaque résolution Timefold est mono-thread côté JVM et CPU-intensive tout le temps
# de son budget (le solveur s'arrête sur une durée, pas un nombre d'itérations — diluer le CPU
# entre trop de résolutions à la fois ne les fait pas durer plus longtemps, ça dégrade leur QUALITÉ
# dans le même budget de temps). Taille fixée une fois au démarrage du process (comme
# _SOLVER_FACTORY_CACHE ci-dessous), sur `settings.SOLVER_MAX_CONCURRENT_SOLVES`.
_SOLVE_SEMAPHORE = threading.Semaphore(settings.SOLVER_MAX_CONCURRENT_SOLVES)


class SolverState:
    """
    État du solveur, indexé par slug de base (voir architecture.md, multi-base) — un attribut de
    CLASSE partagé par tout le process bloquerait à tort une résolution sur la base B pendant
    qu'une résolution tourne sur la base A. `_states` reste néanmoins un dict en mémoire process
    (pas en base, contrairement à exclusive_mode_state) : limite connue si Klepsydrix tournait un
    jour en plusieurs process/instances en parallèle (load balancing) — acceptable tant qu'un seul
    process tourne par déploiement, l'hypothèse implicite de toute l'architecture actuelle du
    solveur (thread du même process, pas un worker séparé).

    `_queue_order`/`_cancel_requested` : suivi de la file d'attente (voir _SOLVE_SEMAPHORE), séparé
    de l'état par base ci-dessus — une file est par nature une notion transverse à toutes les
    bases, pas un état qui appartient à une seule d'entre elles.
    """
    _states: dict = {}
    _queue_lock = threading.Lock()
    _queue_order: list = []
    _cancel_requested: set = set()

    @classmethod
    def _for(cls, slug: str) -> _PerDbSolverState:
        if slug not in cls._states:
            cls._states[slug] = _PerDbSolverState()
        return cls._states[slug]

    @classmethod
    def enqueue(cls, slug: str, kind: str = None, pipeline_total_steps: int = 1):
        """
        Place `slug` en file d'attente — appelé à la fois par les fonctions `start_*_async` (tout
        de suite, dans le thread de la requête HTTP, pour que `/status` reflète l'état QUEUED sans
        attendre que le thread de résolution démarre réellement) et par `_run_job` elle-même
        (idempotent : `_queue_order` n'accumule jamais deux fois le même slug).
        """
        state = cls._for(slug)
        with state.lock:
            state.status = "QUEUED"
            state.progress = None
            state.last_progress_at = None
            state.started_at = None
            state.time_limit_seconds = None
            state.kind = kind
            state.pipeline_step = 1
            state.pipeline_total_steps = pipeline_total_steps
            state.stop_requested = False
        with cls._queue_lock:
            cls._cancel_requested.discard(slug)
            if slug not in cls._queue_order:
                cls._queue_order.append(slug)

    @classmethod
    def dequeue(cls, slug: str):
        """Retire `slug` de la file — un emplacement vient d'être obtenu (ou la file d'attente a
        été annulée)."""
        with cls._queue_lock:
            if slug in cls._queue_order:
                cls._queue_order.remove(slug)
            cls._cancel_requested.discard(slug)

    @classmethod
    def request_cancel_queued(cls, slug: str) -> bool:
        """Demande l'annulation d'un job encore EN FILE (pas encore démarré) — voir stop_solving.
        Retourne False si `slug` n'est plus dans la file (déjà démarré, ou déjà terminé/annulé) :
        l'appelant doit alors essayer d'interrompre une résolution active à la place."""
        with cls._queue_lock:
            if slug in cls._queue_order:
                cls._cancel_requested.add(slug)
                return True
            return False

    @classmethod
    def is_cancel_requested(cls, slug: str) -> bool:
        with cls._queue_lock:
            return slug in cls._cancel_requested

    @classmethod
    def queue_snapshot(cls, slug: str):
        """Position 1-based dans la file (None si pas en file) et longueur totale de la file —
        pour l'affichage IHM (« en file d'attente, position X sur Y »)."""
        with cls._queue_lock:
            position = cls._queue_order.index(slug) + 1 if slug in cls._queue_order else None
            return position, len(cls._queue_order)

    @classmethod
    def set_solving(cls, slug: str, solver, time_limit_seconds=None, kind: str = None, pipeline_step: int = 1, pipeline_total_steps: int = None):
        """
        `pipeline_step`/`pipeline_total_steps` : identifie la phase courante d'un job à plusieurs
        étapes (voir _run_job) — ex. "1/2" puis "2/2" pour le pipeline d'optimisation. Ne PAS
        repasser par NOT_SOLVING entre deux phases d'un même job (voir _run_job) : ce changement
        de phase appelle set_solving() directement, jamais set_not_solving() entre les deux, pour
        éviter un flicker "pas de solve en cours" côté IHM entre les deux étapes.
        """
        state = cls._for(slug)
        with state.lock:
            state.active_solver = solver
            state.status = "SOLVING"
            state.progress = None
            state.last_progress_at = None
            state.started_at = time.monotonic()
            state.time_limit_seconds = time_limit_seconds
            if kind is not None:
                state.kind = kind
            state.pipeline_step = pipeline_step
            if pipeline_total_steps is not None:
                state.pipeline_total_steps = pipeline_total_steps

    @classmethod
    def set_solving_status(cls, slug: str):
        state = cls._for(slug)
        with state.lock:
            state.status = "SOLVING"

    @classmethod
    def set_not_solving(cls, slug: str):
        state = cls._for(slug)
        with state.lock:
            state.active_solver = None
            state.status = "NOT_SOLVING"
            state.progress = None
            state.last_progress_at = None
            state.started_at = None
            state.time_limit_seconds = None
            state.kind = None
            state.pipeline_step = 1
            state.pipeline_total_steps = 1
            state.stop_requested = False

    @classmethod
    def get_status(cls, slug: str):
        state = cls._for(slug)
        with state.lock:
            return state.status

    @classmethod
    def stop_solving(cls, slug: str):
        """
        Deux cas distincts, essayés dans cet ordre : `slug` encore EN FILE (pas encore démarré) →
        annulé sans jamais avoir lu la base ni bloqué l'écriture (voir _run_job) ;
        `slug` déjà EN COURS de résolution → interruption « à la Timefold » via terminate_early()
        (comportement inchangé). Rien à faire si ni l'un ni l'autre (déjà terminé, ou fenêtre très
        étroite entre la sortie de file et l'enregistrement de active_solver — best-effort, comme
        le reste du suivi de progression, voir set_progress ci-dessous).

        `stop_requested` est positionné inconditionnellement (pas seulement dans le cas
        "résolution active") : un pipeline à 2 phases (_run_job) doit aussi pouvoir être interrompu
        PENDANT la mutation entre les deux phases, un moment où aucun solveur n'est actif pour
        que terminate_early() ait quoi que ce soit à intercepter (voir plan salles §4, cas limite).
        """
        state = cls._for(slug)
        with state.lock:
            state.stop_requested = True
        if cls.request_cancel_queued(slug):
            return
        with state.lock:
            if state.active_solver:
                try:
                    state.active_solver.terminate_early()
                except Exception:
                    pass

    @classmethod
    def is_stop_requested(cls, slug: str) -> bool:
        state = cls._for(slug)
        with state.lock:
            return state.stop_requested

    @classmethod
    def set_progress(cls, slug: str, hard_score: int, soft_score: int):
        """
        Throttlé à 1 mise à jour/seconde : le listener Timefold (voir _run_solve_phase) peut
        être notifié plusieurs fois par seconde, surtout pendant la phase de construction — écrire
        à cette fréquence dans un état partagé verrouillé n'apporterait rien, le frontend ne
        pollant /status que toutes les 3s (App.vue::checkStatus). La toute première notification
        d'une résolution passe toujours immédiatement (pas d'attente initiale d'1s à vide).
        """
        now = time.monotonic()
        state = cls._for(slug)
        with state.lock:
            if state.last_progress_at is not None and now - state.last_progress_at < 1.0:
                return
            state.last_progress_at = now
            state.progress = {"hard_score": hard_score, "soft_score": soft_score}

    @classmethod
    def get_snapshot(cls, slug: str):
        """
        Réponse complète pour /status : statut, dernier score connu, temps écoulé/limite, position
        dans la file — tout ce dont le frontend a besoin pour afficher une progression, sans jamais
        exposer l'état interne des entités de la solution (voir la mise en garde dans
        _run_job). `queue_position`/`queue_length` valent None/0 hors statut QUEUED.
        """
        state = cls._for(slug)
        with state.lock:
            elapsed = None if state.started_at is None else round(time.monotonic() - state.started_at, 1)
            status = state.status
            time_limit_seconds = state.time_limit_seconds
            progress = state.progress
            kind = state.kind
            pipeline_step = state.pipeline_step
            pipeline_total_steps = state.pipeline_total_steps
        queue_position, queue_length = cls.queue_snapshot(slug)
        return {
            "status": status,
            "progress": progress,
            "elapsed_seconds": elapsed,
            "time_limit_seconds": time_limit_seconds,
            "queue_position": queue_position,
            "queue_length": queue_length,
            "kind": kind,
            "pipeline_step": pipeline_step,
            "pipeline_total_steps": pipeline_total_steps,
        }


def _build_course_placement_problem(db: Session, school_id: Optional[int] = None) -> PlanningTimetable:
    """
    Domaine COURSE_PLACEMENT (voir plan salles §2) — remplace l'ancien _build_planning_problem :
    ne résout que timeslot/week_type. La salle n'est plus une PlanningVariable ; elle devient une
    ressource contrainte via PlanningCourse.leaf_classroom_ids (salle-feuille précise) et
    PlanningGroupDemand (besoin de groupe), tous deux lus directement depuis les
    classroom_requirements du cours PARENT — la cascade décrémentée (CourseClassroomRequirement)
    garantit déjà que cette collection est correcte, pas d'agrégation bespoke à faire ici.
    """
    db_teachers = db.execute(select(Teacher)).scalars().unique().all()
    db_non_teaching_staffs = db.execute(select(NonTeachingStaff)).scalars().unique().all()
    db_divisions = db.execute(select(Division)).scalars().unique().all()
    
    db_timeslots = Timeslot.get_active_timeslots(db)
    
    # IMPORTANT : Le solveur ne travaille QUE sur les cours de premier niveau.
    # Les cours simples enfants (qui subdivisent un cours composé) sont uniquement
    # utilisés pour l'affichage et le détail des ressources. Le placement global sur
    # la grille horaire est géré exclusivement au niveau du cours parent.
    db_courses = db.execute(select(Course).filter(Course.parent_id == None)).scalars().unique().all()
    db_links = db.execute(select(ClassPartLink)).scalars().unique().all()
    db_preferences = db.execute(select(ResourcePreference)).scalars().unique().all()
    db_constraints = db.execute(select(ResourceConstraint)).scalars().unique().all()
    db_course_constraints = db.execute(select(CourseToCourseConstraint)).scalars().unique().all()
    db_periods = db.execute(select(Period)).scalars().unique().all()

    teachers_map = {t.id: PlanningTeacher(t.id, t.display_name) for t in db_teachers}
    non_teaching_staffs_map = {s.id: PlanningNonTeachingStaff(s.id, s.first_name, s.last_name) for s in db_non_teaching_staffs}
    from backend.app.models.school import School
    sch_limits = {}
    if school_id is not None:
        school_obj = db.execute(select(School).filter(School.id == school_id)).scalars().first()
        if school_obj:
            sch_limits["day"] = school_obj.max_pedagogic_weight_per_day
            sch_limits["morning"] = school_obj.max_pedagogic_weight_per_morning
            sch_limits["afternoon"] = school_obj.max_pedagogic_weight_per_afternoon

    divisions_map = {d.id: PlanningDivision(
        id=d.id,
        name=d.name,
        max_pedagogic_weight_per_day=sch_limits.get("day"),
        max_pedagogic_weight_per_morning=sch_limits.get("morning"),
        max_pedagogic_weight_per_afternoon=sch_limits.get("afternoon")
    ) for d in db_divisions}
    from backend.app.models.system_setting import SystemSetting
    val = SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION")
    std_duration_min = int(val)
    
    max_minutes_by_day = {}
    for ts in db_timeslots:
        if ts.day_of_week not in max_minutes_by_day or ts.minutes_from_midnight > max_minutes_by_day[ts.day_of_week]:
            max_minutes_by_day[ts.day_of_week] = ts.minutes_from_midnight

    timeslots_map = {ts.id: PlanningTimeslot(ts.id, ts.day_of_week, ts.minutes_from_midnight, max_minutes_by_day[ts.day_of_week] + std_duration_min, ts.get_noon_boundary_minutes()) for ts in db_timeslots}

    teachers_list = list(teachers_map.values())
    non_teaching_staffs_list = list(non_teaching_staffs_map.values())
    divisions_list = list(divisions_map.values())
    timeslots_list = list(timeslots_map.values())
    links_list = [PlanningClassPartLink(link.class_part_a_id, link.class_part_b_id) for link in db_links]
    period_to_bit = {p.id: (1 << i) for i, p in enumerate(db_periods)}

    preferences_list = [
        PlanningPreference(
            id=pref.id,
            resource_type=pref.resource_type,
            resource_id=pref.resource_id,
            timeslot_id=pref.timeslot_id,
            preference_level=pref.preference_level,
            week_type=pref.week_type,
            period_ids=[p.id for p in pref.periods],
            period_mask=sum(period_to_bit.get(p.id, 0) for p in pref.periods)
        ) for pref in db_preferences
    ]
    # Sentinelle catch-all pour classroom_group_capacity (constraints.py) : sans elle, la
    # jointure PlanningGroupDemand x PlanningCourse x PlanningPreference perdrait toute demande
    # sans AUCUNE préférence Unsuited applicable (jointure interne classique) — voir plan salles
    # §2.2b et le spike `spike_group_capacity_unsuited_3way.py`. resource_id=-1 : jamais un vrai
    # id de Classroom (toujours positif, auto-incrémenté).
    preferences_list.append(PlanningPreference(
        id=-1, resource_type="__SENTINEL__", resource_id=-1, timeslot_id=-1,
        preference_level="Neutral", week_type="W", period_ids=[], period_mask=0,
    ))
    constraints_list = [
        PlanningResourceConstraint(
            id=rc.id,
            resource_type=rc.resource_type,
            resource_id=rc.resource_id,
            is_optional=False, # Default for ResourceConstraint since it doesn't have it
            max_hours_per_day=rc.max_hours_per_day, # Now rc has max_hours_per_day
            max_hours_per_half_day=None,
            max_hours_per_am=rc.max_hours_per_am,
            max_hours_per_pm=rc.max_hours_per_pm,
            max_presence_days_per_week=rc.max_presence_days_per_week,
            max_presence_hours_per_day=rc.max_presence_hours_per_day,
            late_start_days_per_week=rc.late_start_days_per_week,
            late_start_time=rc.late_start_time,
            early_end_days_per_week=rc.early_end_days_per_week,
            early_end_time=rc.early_end_time,
            min_free_days_per_week=rc.min_free_days_per_week,
            min_free_half_days_per_week=rc.min_free_half_days_per_week,
            max_worked_am_per_week=rc.max_worked_am_per_week,
            max_worked_pm_per_week=rc.max_worked_pm_per_week,
            only_one_half_day_per_day=bool(rc.only_one_half_day_per_day),
            max_gap_hours_per_week=rc.max_gap_hours_per_week or 2
        ) for rc in db_constraints
    ] + [
        PlanningResourceConstraint(
            id=-rc.id,
            resource_type="Subject",
            resource_id=rc.target_subject_a_id,
            target_subject_a_id=rc.target_subject_a_id,
            is_optional=rc.is_optional,
            target_subject_b_id=rc.target_subject_b_id,
            incompatible_same_half_day=bool(rc.incompatible_same_half_day),
            incompatible_same_day=bool(rc.incompatible_same_day),
            incompatible_two_consecutive_days=bool(rc.incompatible_two_consecutive_days),
            min_free_half_days_between=rc.min_free_half_days_between,
            prevent_consecutive_a_then_b=bool(rc.prevent_consecutive_a_then_b),
            prevent_consecutive_b_then_a=bool(rc.prevent_consecutive_b_then_a),
            max_hours_per_day=rc.max_hours_per_day,
            max_hours_per_half_day=rc.max_hours_per_half_day,
            weekly_order=rc.weekly_order.value if rc.weekly_order else "NONE",
            group_course_order=rc.group_course_order.value if rc.group_course_order else "NONE",
            max_separation=rc.max_separation.value if rc.max_separation else "NONE",
            division_ids=[d.id for d in rc.divisions] if rc.divisions else [],
            max_hours_per_am=None,
            max_hours_per_pm=None,
            max_presence_days_per_week=None,
            max_presence_hours_per_day=None,
            late_start_days_per_week=None,
            late_start_time=None,
            early_end_days_per_week=None,
            early_end_time=None,
            min_free_days_per_week=None,
            min_free_half_days_per_week=None,
            max_worked_am_per_week=None,
            max_worked_pm_per_week=None,
            only_one_half_day_per_day=False,
            max_gap_hours_per_week=2
        ) for rc in db.execute(select(SubjectToSubjectConstraint)).scalars().unique().all()
    ]

    course_constraints_list = [
        PlanningCourseToCourseConstraint(
            id=cc.id,
            type=cc.type,
            scope=cc.scope or "SLOT",
            custom_half_days=cc.custom_half_days,
            course_ids=[c.id for c in cc.courses],
            is_optional=cc.is_optional,
            label=cc.label
        ) for cc in db_course_constraints
    ]

    from backend.app.models.classroom_closure import leaf_classroom_ids_under

    courses_list = []
    group_demands_list = []
    for c in db_courses:
        ts_planning = timeslots_map.get(c.timeslot_id) if c.timeslot_id else None

        # Gestion multi-établissement (US2) :
        # Si school_id est spécifié et que ce cours appartient à une AUTRE école, il est forcé à
        # is_pinned = True pour ne pas être déplacé par le solveur — inconditionnellement, placé
        # ou non. Exempter les cours étrangers non placés semblait cohérent avec la règle modèle
        # (Course.validate_pinned_requires_timeslot) mais réintroduit le coût de recherche
        # inutile (CH/LS explorant des cours jamais réécrits en base, voir plus bas) pour la
        # portion — potentiellement significative — d'une autre école qui n'est pas encore
        # placée. Epingler un cours non placé reste parfaitement légal côté Timefold (timeslot
        # autorise déjà l'absence de valeur).
        is_pinned = c.is_pinned
        if school_id is not None and c.school_id != school_id:
            is_pinned = True

        # Salle (voir plan salles §2.1) : leaf_classroom_ids est un simple fait, pas une
        # PlanningVariable — pas de risque "pinned to null" ici (contrairement à l'ancien
        # classroom), donc pas de salle virtuelle nécessaire pour un cours épinglé sans salle.
        leaf_classroom_ids = [
            r.classroom_id for r in c.classroom_requirements if not r.classroom.children_classrooms
        ]
        for r in c.classroom_requirements:
            if not r.classroom.children_classrooms:
                continue  # salle-feuille précise, déjà comptée ci-dessus
            group_demands_list.append(PlanningGroupDemand(
                course_id=c.id,
                demand_key=f"{c.id}:{r.classroom_id}",
                group_id=r.classroom_id,
                needed_count=r.quantity,
                group_leaf_ids=leaf_classroom_ids_under(db, r.classroom_id),
            ))

        # Charger week_type et class_part_ids
        # Phase C (voir attribution_week_type_auto.md, Échanges 17-19) : tout cours dont le
        # week_type BDD (c.week_type — agrégat _sync_parent_week_type pour un cours composé)
        # est A, B ou Q reçoit un vrai choix {A, B} au solveur ; W reste seul et intact
        # (aucun cours W ne doit jamais devenir A/B, voir spec.md). Ceci s'applique aussi bien
        # aux cours composés qu'aux cours simples : _sync_parent_week_type garantit qu'un
        # parent composé n'affiche A/B/Q QUE si TOUS ses enfants partagent uniformément cette
        # même valeur — la cascade au write-back ci-dessous peut donc reporter sans ambiguïté
        # la lettre choisie par le solveur à tous les enfants.
        # Valeur de départ : None pour un cours Q (un spike dédié a confirmé qu'une valeur hors
        # du range déclaré, ex: laisser "Q" avec un range ["A","B"], n'est pas réévaluée par le
        # solveur et peut y rester bloquée ; None est en revanche pris en charge nativement,
        # comme timeslot/classroom, avec un résultat final identique quelle que soit la valeur
        # de départ légale choisie — le pré-semage n'apporte donc rien et a été retiré). Pour un
        # cours déjà résolu A/B, la valeur de départ reste sa valeur actuelle (point de départ
        # naturel pour la recherche, comme pour classroom, § 12.B d'architecture.md) — rien
        # n'empêche pour autant le solveur de la faire basculer si c'est meilleur.
        original_week_type = c.week_type.value
        if original_week_type == "W":
            week_type = "W"
            week_type_range = ["W"]
        elif original_week_type == "Q":
            week_type = None
            week_type_range = ["A", "B"]
        else:
            week_type = original_week_type
            week_type_range = ["A", "B"]

        # Même risque que pour classroom ci-dessus, pour la même raison : week_type n'autorise
        # pas non plus l'absence de valeur ("pinned to null..."). None est sans risque pour un
        # cours Q non épinglé (CH le réévalue), mais un cours épinglé n'est JAMAIS réévalué — y
        # laisser None le bloquerait dans un état illégal. Contrairement à classroom, pas besoin
        # d'une valeur virtuelle hors range : week_type_range[0] (A ou B, un simple label sans
        # notion d'unicité globale comme un id de salle) ne peut jamais créer de conflit fantôme
        # — la comparaison de semaine ne compte de toute façon que pour des cours qui se
        # chevauchent réellement en temps (_courses_overlap_in_time exclut déjà tout cours non
        # placé, timeslot=None y compris).
        if is_pinned and week_type is None:
            week_type = week_type_range[0]
        class_part_ids = []
        division_ids = set([d.id for d in c.divisions]) if c.divisions else set()
            
        if c.groups:
            for grp in c.groups:
                for cp in grp.class_parts:
                    class_part_ids.append(cp.id)
                    if cp.division_id:
                        division_ids.add(cp.division_id)
        if c.divisions:
            for div in c.divisions:
                for part in div.partitions:
                    class_part_ids.extend([cp.id for cp in part.class_parts])
            
        if c.class_parts:
            for cp in c.class_parts:
                class_part_ids.append(cp.id)
                if cp.division_id:
                    division_ids.add(cp.division_id)
                    
        class_part_ids = list(set(class_part_ids))
            
        from backend.app.models.subject import Subject
        pedagogic_weight = 0.0
        if c.subject_id:
            subj = db.execute(select(Subject).filter(Subject.id == c.subject_id)).scalars().first()
            if subj and subj.pedagogic_weight:
                pedagogic_weight = subj.pedagogic_weight

        p_ids = (
            [p.id for p in c.periods]
            if c.periods
            else (
                [p.id for p in db_periods if p.period_type_id == c.period_type_id]
                if c.period_type_id
                else [p.id for p in db_periods]
            )
        )
        pc = PlanningCourse(
            id=c.id,
            subject_id=c.subject_id,
            teachers=[teachers_map[t.id] for t in c.teachers if t.id in teachers_map],
            non_teaching_staffs=[non_teaching_staffs_map[s.id] for s in c.non_teaching_staffs if s.id in non_teaching_staffs_map],
            divisions=[divisions_map[d.id] for d in c.divisions if d.id in divisions_map],
            timeslot=ts_planning,
            leaf_classroom_ids=leaf_classroom_ids,
            is_pinned=is_pinned,
            original_timeslot_id=c.timeslot_id,
            parent_id=getattr(c, 'parent_id', None),
            pedagogic_weight_total=pedagogic_weight * (c.duration_minutes / 60.0),
            week_type=week_type,
            week_type_range=week_type_range,
            class_part_ids=class_part_ids,
            all_division_ids=list(division_ids),
            is_full_class=(len(c.divisions) > 0 and len(c.groups) == 0 and len(c.class_parts) == 0),
            period_ids=p_ids,
            period_mask=sum(period_to_bit.get(pid, 0) for pid in p_ids),
            duration_minutes=c.duration_minutes
        )
        courses_list.append(pc)

    return PlanningTimetable(
        teachers=teachers_list,
        non_teaching_staffs=non_teaching_staffs_list,
        divisions=divisions_list,
        timeslots=timeslots_list,
        courses=courses_list,
        class_part_links=links_list,
        preferences=preferences_list,
        resource_constraints=constraints_list,
        course_to_course_constraints=course_constraints_list,
        group_demands=group_demands_list,
        score=None,
    )

# Cache process-vie du SolverFactory (voir backend/experimental_java_heatmap/README.md § 5.1) :
# SolverFactory.create() traduit le bytecode Python de constraints.py/PlanningCourse en classes
# JVM — un coût mesuré ~0.6-0.9s, indépendant des données, qui ne dépend QUE du code source
# (constraints.py, domain.py), jamais rebuilt tant que le process tourne. Aucun termination_config
# n'est baké ici : les limites de temps du solveur (settings.SOLVER_*, y compris les overrides de
# test) doivent rester dynamiques — passées via solver_config_override à build_solver() (voir
# _run_solve_phase), sans jamais retraduire le bytecode. Double-checked locking : plusieurs
# threads peuvent appeler _get_solver_factory() concurremment (solve async + heatmap), on ne veut
# construire qu'une seule fois.
_SOLVER_FACTORY_CACHE = None
_SOLVER_FACTORY_LOCK = threading.Lock()

def _get_solver_factory():
    global _SOLVER_FACTORY_CACHE
    if _SOLVER_FACTORY_CACHE is None:
        with _SOLVER_FACTORY_LOCK:
            if _SOLVER_FACTORY_CACHE is None:
                solver_config = SolverConfig(
                    environment_mode=EnvironmentMode.NO_ASSERT,
                    solution_class=PlanningTimetable,
                    entity_class_list=[PlanningCourse],
                    score_director_factory_config=ScoreDirectorFactoryConfig(
                        constraint_provider_function=define_constraints
                    ),
                )
                _SOLVER_FACTORY_CACHE = SolverFactory.create(solver_config)
    return _SOLVER_FACTORY_CACHE

def _write_back_course_placement(db, school_id, solution):
    """Écrit le résultat d'un solve COURSE_PLACEMENT (timeslot + week_type) en base.

    ATTENTION ARCHITECTURE : Le solveur n'appelle JAMAIS la méthode Course.update() du CRUDMixin
    pour des raisons de performances (éviter de déclencher des milliers de validations Pydantic/
    Python). Il assigne directement les attributs (Direct Attribute Assignment) et laisse
    l'appelant faire le commit. CONSÉQUENCE : Toute règle métier vérifiée dans
    `Course.validate_placement_conflicts()` (ex: débordement de grille) DOIT obligatoirement être
    dupliquée en tant que contrainte Timefold dans `constraints.py`, sinon l'IA contournera la
    sécurité lors de la sauvegarde. Ne fait PAS le commit — à la charge de l'appelant.
    """
    for pc in solution.courses:
        db_course = db.get(Course, pc.id)
        if not db_course:
            continue
        # Filet de sécurité (US2, multi-établissement) : un cours d'une autre école que
        # celle demandée est déjà épinglé (donc jamais réellement déplacé, voir
        # _build_planning_problem) — mais on n'écrit quand même jamais son résultat en
        # retour, pour ne dépendre d'aucune garantie interne au solveur pour protéger les
        # données d'une école qu'on n'est pas censé modifier.
        if school_id is not None and db_course.school_id != school_id:
            continue
        db_course._via_crud_mixin_update = True
        db_course.timeslot_id = pc.timeslot.id if pc.timeslot else None
        # week_type_before : capturé AVANT l'écriture ci-dessous, pour pouvoir détecter
        # une résolution/permutation réelle (Q->A/B ou A<->B) et déclencher la cascade
        # aux enfants d'un cours composé (voir plus bas) — sans quoi on écraserait la
        # référence nécessaire à la comparaison. Pour un cours en W, pc.week_type_range
        # n'a jamais eu qu'une seule valeur légale (voir _build_planning_problem), donc
        # pc.week_type est structurellement resté égal à sa valeur d'entrée : l'écriture
        # est un no-op sans risque dans ce cas.
        week_type_before = db_course.week_type.value
        db_course.week_type = pc.week_type
        # Salle : plus écrite ici — COURSE_PLACEMENT ne résout plus que timeslot/
        # week_type (voir plan salles §2). L'attribution des salles précises est du
        # ressort du domaine CLASSROOM_ASSIGNMENT (room_constraints.py, tâche #6).
        if db_course.is_composed:
            # Synchroniser le timeslot de chaque cours enfant par rapport au parent
            from backend.app.models.timeslot import Timeslot
            parent_ts = db.get(Timeslot, db_course.timeslot_id) if db_course.timeslot_id else None
            # Cascade du week_type aux enfants : seulement si le solveur a réellement
            # changé le week_type du parent pendant le solving (Q->A, Q->B, ou A<->B —
            # peu importe lequel, il suffit de comparer à la valeur d'avant solve) — pas
            # à chaque solve, sinon un cours composé stable (resté sur sa lettre) verrait
            # ses enfants réécrits sans raison. Sûr car _sync_parent_week_type garantit
            # qu'un parent affichant une valeur singleton (A/B/Q) avant résolution la
            # partageait avec 100% de ses enfants (voir attribution_week_type_auto.md,
            # Échange 18/19/20) : reporter la même lettre à tous, sans distinction, est
            # donc toujours correct ici.
            week_type_changed = pc.week_type != week_type_before
            for child in db_course.children:
                child._via_crud_mixin_update = True
                if parent_ts:
                    child.timeslot_id = parent_ts.get_offset_timeslot(db, child.parent_timeslot_offset)
                else:
                    child.timeslot_id = None
                if week_type_changed:
                    child.week_type = pc.week_type
                child.recompute_status()

        db_course.recompute_status()


# ---------------------------------------------------------------------------------------------
# Orchestration générique des 3 points d'entrée Timefold (plan salles §4) — COURSE_PLACEMENT seul
# (/course-placement), CLASSROOM_ASSIGNMENT seul (/classroom-assignment), et le pipeline à 2
# phases (/optimize). Le legacy /solve (domaine combiné timeslot+week_type+classroom) a été
# retiré une fois test_solver.py migré vers ces 3 points d'entrée (voir plan salles §4, décision
# produit) — cette orchestration est désormais le seul chemin de résolution.
# ---------------------------------------------------------------------------------------------

def _run_job(school_id, slug, kind, phases, db_session=None):
    """
    Point d'entrée générique pour un job Timefold à 1 ou 2 phases. `phases` : liste de 1 (solve
    simple) ou 2 (pipeline /optimize) dicts, voir _run_solve_phase pour leur contenu.
    """
    if db_session is not None:
        db = db_session
        slug = slug or db_registry.slug_for_engine(db.bind) or DEFAULT_DB_NAME
    else:
        slug = slug or DEFAULT_DB_NAME
        db = db_registry.sessionmaker_for(slug)()

    SolverState.enqueue(slug, kind=kind, pipeline_total_steps=len(phases))
    acquired = False
    try:
        while not acquired:
            acquired = _SOLVE_SEMAPHORE.acquire(timeout=0.5)
            if not acquired and SolverState.is_cancel_requested(slug):
                SolverState.dequeue(slug)
                SolverState.set_not_solving(slug)
                return None
        SolverState.dequeue(slug)
        SolverState.set_solving_status(slug)
        return _run_job_phases(db, db_session, school_id, slug, kind, phases)
    finally:
        if acquired:
            _SOLVE_SEMAPHORE.release()


def _run_job_phases(db, db_session, school_id, slug, kind, phases):
    """
    Exécute les 1 ou 2 phases du job l'une après l'autre, dans une seule fenêtre de mode exclusif
    (une seule entrée/sortie, pas une par phase — voir plan salles §4). Commits intermédiaires
    après chaque phase et après chaque mutation, pour la résilience (le mode exclusif reste actif
    en base tout du long, ces commits ne rouvrent l'écriture à personne d'autre que cette
    session).

    Cas limite documenté au plan §4 : arrêt demandé PENDANT la mutation intermédiaire d'un
    pipeline à 2 phases (le remplacement salle précise -> groupe, entre 4a et 4b) — ce n'est pas
    un solve Timefold, `solver.terminate_early()` n'a donc rien à intercepter à ce moment.
    `SolverState.is_stop_requested` est donc consulté explicitement à DEUX points par phase, pas
    seulement pendant `solver.solve()` : juste avant la mutation elle-même, et juste avant de
    lancer la phase suivante — sans quoi un stop pendant la mutation laisserait les salles remises
    à l'état "groupe" sans jamais être réattribuées.
    """
    entered_exclusive = False
    try:
        enter_exclusive_mode(db, user="admin")
        entered_exclusive = True
        db.info["bypass_exclusive_mode"] = True

        total_steps = len(phases)
        last_solution = None
        for step_index, phase in enumerate(phases, start=1):
            if SolverState.is_stop_requested(slug):
                break

            mutation_before = phase.get("mutation_before")
            if mutation_before is not None:
                mutation_before(db)
                db.commit()
                if SolverState.is_stop_requested(slug):
                    break

            last_solution = _run_solve_phase(
                db, slug,
                phase_kind=phase["kind"],
                build_fn=phase["build_fn"],
                solver_factory_fn=phase["solver_factory_fn"],
                termination_config=phase["termination_config"],
                write_back_fn=phase["write_back_fn"],
                school_id=school_id,
                pipeline_step=step_index,
                pipeline_total_steps=total_steps,
            )
            db.commit()

        # exit_exclusive_mode_and_rotate_token ne commit pas elle-même : sa mise à jour part dans
        # LE MÊME commit que le résultat de la dernière phase exécutée — même raisonnement
        # d'atomicité que le write-back solveur en général (même schéma partout dans ce fichier).
        exit_exclusive_mode_and_rotate_token(db)
        db.commit()
        return last_solution

    except Exception as e:
        db.rollback()
        logger.error("Job thread error: %s", e)
        if entered_exclusive:
            try:
                clear_exclusive_mode(db)
            except Exception:
                db.rollback()
        raise e
    finally:
        if not db_session:
            db.close()
        SolverState.set_not_solving(slug)


def _run_solve_phase(db, slug, phase_kind, build_fn, solver_factory_fn, termination_config, write_back_fn,
                      school_id, pipeline_step, pipeline_total_steps):
    """
    Une phase = construire le problème, lancer un solve avec le TerminationConfig de CETTE phase,
    écrire le résultat en base (write_back_fn ne commit pas — _run_job_phases s'en charge après
    chaque phase). set_solving() est appelé directement (jamais set_not_solving() entre deux
    phases, voir SolverState.set_solving) pour que le passage 1/2 -> 2/2 n'affiche jamais de
    "pas de solve en cours" côté IHM.
    """
    problem = build_fn(db, school_id)
    solver_factory = solver_factory_fn()
    solver = solver_factory.build_solver(solver_config_override=SolverConfigOverride(
        termination_config=termination_config,
    ))

    SolverState.set_solving(slug, solver, kind=phase_kind, pipeline_step=pipeline_step, pipeline_total_steps=pipeline_total_steps)

    # Même mise en garde qu'ailleurs dans ce fichier : ne jamais lire les champs des entités de
    # event.new_best_solution ici, seul event.new_best_score est sûr (voir son commentaire pour le
    # détail des deux limitations connues du paquet timefold 1.24.0b0 installé).
    def _on_best_solution_changed(event):
        score = event.new_best_score
        SolverState.set_progress(
            slug,
            score.hard_score if hasattr(score, 'hard_score') else 0,
            score.soft_score if hasattr(score, 'soft_score') else 0,
        )

    solver.add_event_listener(_on_best_solution_changed)

    solution = solver.solve(problem)
    write_back_fn(db, school_id, solution)
    return solution


def _course_placement_termination_config(*, best_score_feasible: bool, spent_limit_seconds: int,
                                          unimproved_spent_limit_seconds: Optional[int] = None) -> TerminationConfig:
    """
    /course-placement (endpoint 2, plan salles §4) : s'arrête à la 1ère solution faisable OU au
    plafond de durée, le premier atteint — best_score_feasible=True. /optimize étape 1/2
    (endpoint 4a) : PAS de best_score_feasible (on veut le budget de calcul complet, pas le
    premier arrêt venu), juste une durée max et une durée sans amélioration — les deux passent par
    cette même fonction, `best_score_feasible` distinguant les deux cas.
    """
    if best_score_feasible:
        return TerminationConfig(
            best_score_feasible=True,
            termination_config_list=[
                TerminationConfig(best_score_feasible=True),
                TerminationConfig(spent_limit=Duration(seconds=spent_limit_seconds)),
            ],
            termination_composition_style=TerminationCompositionStyle.OR,
        )
    return TerminationConfig(
        spent_limit=Duration(seconds=spent_limit_seconds),
        unimproved_spent_limit=Duration(seconds=unimproved_spent_limit_seconds) if unimproved_spent_limit_seconds else None,
    )


def start_course_placement_async(school_id: Optional[int] = None, slug: Optional[str] = None):
    """POST /course-placement (endpoint 2, plan salles §4) — remplace « Générer », résout
    timeslot/week_type seuls (domaine COURSE_PLACEMENT), s'arrête à la 1ère solution faisable ou
    au plafond SOLVER_COURSE_PLACEMENT_CEILING_SECONDS."""
    slug = slug or DEFAULT_DB_NAME
    if SolverState.get_status(slug) in ("SOLVING", "QUEUED"):
        return
    SolverState.enqueue(slug, kind="COURSE_PLACEMENT", pipeline_total_steps=1)
    termination_config = _course_placement_termination_config(
        best_score_feasible=True,
        spent_limit_seconds=settings.SOLVER_COURSE_PLACEMENT_CEILING_SECONDS,
    )
    phases = [{
        "kind": "COURSE_PLACEMENT",
        "build_fn": _build_course_placement_problem,
        "solver_factory_fn": _get_solver_factory,
        "termination_config": termination_config,
        "write_back_fn": lambda db, school_id, solution: _write_back_course_placement(db, school_id, solution),
    }]
    thread = threading.Thread(target=_run_job, kwargs={
        "school_id": school_id, "slug": slug, "kind": "COURSE_PLACEMENT", "phases": phases,
    })
    thread.daemon = True
    thread.start()


def start_classroom_assignment_async(school_id: Optional[int] = None, slug: Optional[str] = None):
    """POST /classroom-assignment (endpoint 3, plan salles §4) — « Attribuer les salles »,
    résout la salle précise (domaine CLASSROOM_ASSIGNMENT) sur tous les cours porteurs d'une
    exigence de groupe, mêmes conditions d'arrêt (durée/sans-amélioration) que le point d'entrée COURSE_PLACEMENT en dehors du cas best_score_feasible."""
    from backend.app.solver.room_solver import (
        _build_classroom_assignment_problem,
        _get_classroom_assignment_solver_factory,
        _write_back_classroom_assignment,
    )
    slug = slug or DEFAULT_DB_NAME
    if SolverState.get_status(slug) in ("SOLVING", "QUEUED"):
        return
    SolverState.enqueue(slug, kind="CLASSROOM_ASSIGNMENT", pipeline_total_steps=1)
    termination_config = TerminationConfig(
        spent_limit=Duration(seconds=settings.SOLVER_TIME_LIMIT_SECONDS),
        unimproved_spent_limit=Duration(seconds=settings.SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS),
    )
    phases = [{
        "kind": "CLASSROOM_ASSIGNMENT",
        "build_fn": _build_classroom_assignment_problem,
        "solver_factory_fn": _get_classroom_assignment_solver_factory,
        "termination_config": termination_config,
        "write_back_fn": lambda db, school_id, solution: _write_back_classroom_assignment(db, solution),
    }]
    thread = threading.Thread(target=_run_job, kwargs={
        "school_id": school_id, "slug": slug, "kind": "CLASSROOM_ASSIGNMENT", "phases": phases,
    })
    thread.daemon = True
    thread.start()


def start_optimize_pipeline_async(
    school_id: Optional[int],
    slug: Optional[str],
    max_compute_seconds: int,
    max_no_progress_seconds: int,
    replace_rooms_with_groups: bool,
    max_compute_classroom_seconds: Optional[int] = None,
    max_no_progress_classroom_seconds: Optional[int] = None,
):
    """POST /optimize (endpoint 4a/4b, plan salles §4) — pipeline 1 ou 2 phases dans une seule
    fenêtre de mode exclusif : 4a (COURSE_PLACEMENT, budget complet, pas de best_score_feasible)
    puis, si `replace_rooms_with_groups`, la mutation "salle précise -> groupe parent" et 4b
    (CLASSROOM_ASSIGNMENT)."""
    from backend.app.solver.room_solver import (
        _build_classroom_assignment_problem,
        _get_classroom_assignment_solver_factory,
        _write_back_classroom_assignment,
    )
    slug = slug or DEFAULT_DB_NAME
    if SolverState.get_status(slug) in ("SOLVING", "QUEUED"):
        return

    phases = [{
        "kind": "OPTIMIZE_COURSE_PLACEMENT",
        "build_fn": _build_course_placement_problem,
        "solver_factory_fn": _get_solver_factory,
        "termination_config": _course_placement_termination_config(
            best_score_feasible=False,
            spent_limit_seconds=max_compute_seconds,
            unimproved_spent_limit_seconds=max_no_progress_seconds,
        ),
        "write_back_fn": lambda db, school_id, solution: _write_back_course_placement(db, school_id, solution),
    }]
    if replace_rooms_with_groups:
        classroom_spent_limit = max_compute_classroom_seconds or settings.SOLVER_TIME_LIMIT_SECONDS
        classroom_unimproved_limit = max_no_progress_classroom_seconds or settings.SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS
        phases.append({
            "kind": "OPTIMIZE_CLASSROOM_ASSIGNMENT",
            "mutation_before": _reset_classroom_requirements_to_groups,
            "build_fn": _build_classroom_assignment_problem,
            "solver_factory_fn": _get_classroom_assignment_solver_factory,
            "termination_config": TerminationConfig(
                spent_limit=Duration(seconds=classroom_spent_limit),
                unimproved_spent_limit=Duration(seconds=classroom_unimproved_limit),
            ),
            "write_back_fn": lambda db, school_id, solution: _write_back_classroom_assignment(db, solution),
        })

    # kind au niveau job = celui de la 1ère phase (toujours COURSE_PLACEMENT, voir plan) — chaque
    # phase écrase ensuite ce kind avec le sien propre via set_solving() dans _run_solve_phase.
    kind = "OPTIMIZE_COURSE_PLACEMENT"
    SolverState.enqueue(slug, kind=kind, pipeline_total_steps=len(phases))
    thread = threading.Thread(target=_run_job, kwargs={
        "school_id": school_id, "slug": slug, "kind": kind, "phases": phases,
    })
    thread.daemon = True
    thread.start()


def _reset_classroom_requirements_to_groups(db):
    """
    Mutation intermédiaire du pipeline /optimize (4a -> 4b, plan salles §4, case "remplacer les
    salles par leur groupe") : chaque exigence de salle PRÉCISE dont la salle a un parent est
    remontée d'un cran vers ce parent (classroom_id = classroom.parent_classroom_id) — remontée
    d'UN SEUL cran, pas jusqu'à la racine (comportement voulu, décidé en amont, voir "Décisions
    déjà tranchées"). Écriture directe bulk (pas de passage par CourseClassroomRequirement.create()/
    update()) — même raisonnement que le reste du write-back solveur (§1.5, Option 2 assumée ICI
    car ce n'est pas la cascade de décrémentation qui est en jeu, juste un déplacement d'un cran).
    Fusionne les exigences qui remontent vers le même groupe sur un même cours (contrainte
    d'unicité (course_id, classroom_id)) plutôt que d'échouer ou de laisser un doublon. Une
    exigence déjà au niveau groupe, ou une salle sans parent (racine), n'est jamais concernée.
    Ne fait PAS le commit — à la charge de l'appelant (_run_job_phases).
    """
    reqs = db.execute(select(CourseClassroomRequirement)).scalars().unique().all()
    by_course = {}
    for req in reqs:
        by_course.setdefault(req.course_id, []).append(req)

    for course_id, course_reqs in by_course.items():
        existing_by_classroom = {r.classroom_id: r for r in course_reqs}
        for req in course_reqs:
            classroom = req.classroom
            if classroom.parent_classroom_id is None or classroom.children_classrooms:
                continue  # racine (rien à remonter), ou déjà un groupe (rien à remonter deux fois)
            parent_id = classroom.parent_classroom_id
            target = existing_by_classroom.get(parent_id)
            if target is not None and target is not req:
                target._via_crud_mixin_update = True
                target.quantity += req.quantity
                req._via_crud_mixin_delete = True
                db.delete(req)
            else:
                req._via_crud_mixin_update = True
                req.classroom_id = parent_id
                existing_by_classroom[parent_id] = req


def explain_timetable_score(db: Session, school_id: Optional[int] = None) -> dict:
    problem = _build_course_placement_problem(db, school_id)
    solver_factory = _get_solver_factory()
    solution_manager = SolutionManager.create(solver_factory)
    score_explanation = solution_manager.explain(problem)
    score = score_explanation.score
    
    matches_detail = {}
    for cmt in score_explanation.constraint_match_total_map.values():
        matches_detail[cmt.constraint_ref.constraint_name] = {
            "hard": cmt.score.hard_score if hasattr(cmt.score, 'hard_score') else 0,
            "soft": cmt.score.soft_score if hasattr(cmt.score, 'soft_score') else 0,
            "count": len(cmt.constraint_match_set)
        }

    # Calcul d'un score soft épuré de la pénalité artificielle d'Overconstrained Planning
    original_soft_score = score.soft_score if score else 0
    unassigned_constraint_name = "Pénaliser les cours non assignés (Overconstrained Planning)"
    unassigned_soft_impact = 0
    if unassigned_constraint_name in matches_detail:
        unassigned_soft_impact = matches_detail[unassigned_constraint_name]["soft"]
        
    clean_soft_score = original_soft_score - unassigned_soft_impact

    return {
        "hard_score": score.hard_score if score else 0,
        "soft_score": clean_soft_score,
        "summary": score_explanation.summary,
        "matches": matches_detail
    }

def calculate_course_heatmap(db: Session, course_id: int, school_id: Optional[int] = None) -> dict:
    """
    ⚠️ Ne passe JAMAIS par `_SOLVE_SEMAPHORE`/la file d'attente (voir architecture.md, "Concurrence
    des résolutions") — délibéré, pas un oubli. La heatmap n'exécute aucune résolution complète
    (jamais `solver.solve()`, jamais de phase de recherche locale) : elle appelle directement
    `HeatmapEvaluator.calculateIsofunctionalHeatmap` sur le `ScoreDirectorFactory`, un simple calcul
    de score répété sur chaque créneau candidat — nettement moins coûteux en CPU qu'une résolution
    complète, et surtout SYNCHRONE dans le thread de la requête HTTP elle-même (pas de thread
    d'arrière-plan comme les résolutions elles-mêmes) : la mettre derrière la même file d'attente
    qu'un solve de plusieurs minutes la ferait attendre potentiellement aussi longtemps, alors
    qu'elle doit rester réactive (l'IHM l'appelle en direct au survol/à la sélection d'un cours).
    Reste néanmoins soumise à la contention CPU RÉELLE d'un solve concurrent en cours sur une AUTRE
    base (même JVM partagée par tout le process, voir §9.F/G) — ralentie, jamais mise en attente.
    """
    problem = _build_course_placement_problem(db, school_id)
    solver_factory = _get_solver_factory()
    
    # --- EXPERIMENTAL JAVA HOOK ---
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
    
    try:
        from backend.experimental_java_heatmap.heatmap_proxy import calculate_heatmap_java
        return calculate_heatmap_java(problem, solver_factory, course_id)
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}
    # ------------------------------
    
    """
    solution_manager = SolutionManager.create(solver_factory)
    
    # Trouver le cours concerné
    target_course = next((c for c in problem.courses if c.id == course_id), None)
    if not target_course:
        return {}
        
    original_timeslot = target_course.timeslot
    heatmap = {}
    
    # Calculer le score de base sans le cours
    target_course.timeslot = None
    base_explanation = solution_manager.explain(problem)
    base_hard = base_explanation.score.hard_score if hasattr(base_explanation.score, 'hard_score') else 0
    base_soft = base_explanation.score.soft_score if hasattr(base_explanation.score, 'soft_score') else 0

    for ts in problem.timeslots:
        target_course.timeslot = ts
        # Utiliser update() pour être ultra rapide sur les créneaux verts
        score = solution_manager.update(problem)
        
        current_hard = score.hard_score if hasattr(score, 'hard_score') else 0
        current_soft = score.soft_score if hasattr(score, 'soft_score') else 0
        
        delta_hard = current_hard - base_hard
        delta_soft = current_soft - base_soft
        
        reasons = []
        # N'expliquer que s'il y a une dégradation (pour la performance)
        if delta_hard < 0 or delta_soft < 0:
            explanation = solution_manager.explain(problem)
            for constraint_name, cmt in explanation.constraint_match_total_map.items():
                base_cmt = base_explanation.constraint_match_total_map.get(constraint_name)
                
                cur_hard = cmt.score.hard_score if hasattr(cmt.score, 'hard_score') else 0
                cur_soft = cmt.score.soft_score if hasattr(cmt.score, 'soft_score') else 0
                
                b_hard = base_cmt.score.hard_score if base_cmt and hasattr(base_cmt.score, 'hard_score') else 0
                b_soft = base_cmt.score.soft_score if base_cmt and hasattr(base_cmt.score, 'soft_score') else 0
                
                diff_hard = cur_hard - b_hard
                diff_soft = cur_soft - b_soft
                
                # Si cette contrainte s'est aggravée par rapport au score de base
                if diff_hard < 0 or diff_soft < 0:
                    reasons.append({
                        "name": cmt.constraint_ref.constraint_name,
                        "impact_hard": diff_hard,
                        "impact_soft": diff_soft
                    })
                    
        heatmap[str(ts.id)] = {
            "hard": delta_hard,
            "soft": delta_soft,
            "reasons": reasons
        }
        
    # Remettre à l'état initial
    target_course.timeslot = original_timeslot
    
    return heatmap
    """

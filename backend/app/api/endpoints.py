from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Dict, Any, Optional

from backend.app.core.database import get_db
from backend.app.core import db_registry
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.models.course_classroom_requirement import CourseClassroomRequirement
from backend.app.models.non_teaching_staff import NonTeachingStaff
from backend.app.models.group import Group
from backend.app.models.constraint import ResourceConstraint, SubjectToSubjectConstraint
from backend.app.solver.solver import (
    start_course_placement_async,
    start_classroom_assignment_async,
    SolverState,
)

router = APIRouter(prefix="/api/timetable")


def _require_course_access(db: Session, operation: str):
    """
    Ces routes ne passent pas par le CRUD générique (score/heatmap/simulate calculent des données
    dérivées, solve/stop pilotent un thread, reset/simulate/apply-change interrogent Course
    directement plutôt que via Course.read()) — donc aucune protection automatique du moteur de
    droits (voir base.py::CRUDMixin) ne s'applique ici. Vérification explicite, portant sur le
    MODÈLE Course : ces routes agissent sur TOUS les cours à la fois, jamais sur un cours précis.

    D'où un traitement dissymétrique entre lecture et écriture (voir architecture.md §18.F) :
    - **lecture** (score, heatmap, simulate-change) : le droit `perm_read` suffit. Un domaine
      restrictif n'est pas appliqué — ces routes renvoient des agrégats calculés sur l'ensemble
      des cours, limite assumée et documentée ;
    - **écriture** (placement, attribution des salles, stop, reset, apply-change) : le droit
      `perm_write` ne suffit PAS s'il est assorti d'un domaine. Un domaine signifie « vous
      pouvez écrire sur CE sous-ensemble » ; or ces routes ne savent pas se restreindre à un
      sous-ensemble. Les laisser passer reviendrait à écrire sur des cours hors du domaine —
      exactement ce que le domaine interdit. Refus, plutôt qu'une écriture qui déborde.

    **Fail-closed sur le drapeau absent**, contrairement au reste du moteur de droits (base.py,
    generic.py::_check_rpc_access) qui traite son absence comme un mode système légitime. La
    différence tient au point d'appel : ces fonctions-là sont aussi traversées par du code interne
    (seed, cascades, `@constrains`, solveur), qui doit voir toutes les données ; `_require_course_
    access` n'est appelée QUE depuis des routes HTTP, où `current_db_user` a nécessairement déjà
    posé le drapeau (dépendance de routeur, garantie au démarrage par `core/route_guard.py`). Un
    drapeau absent ici ne peut donc signaler qu'un câblage cassé — cas où laisser passer une
    résolution ou une remise à zéro sur l'intégralité des cours serait le pire des comportements.
    """
    user_id = getattr(db, "klepsydrix_user_id", None)
    if user_id is None:
        raise RuntimeError(
            "_require_course_access appelée sans db.klepsydrix_user_id : cette fonction n'est "
            "appelée que depuis des routes HTTP, où current_db_user pose toujours le drapeau. "
            "Son absence signale un câblage de routage cassé, pas un mode système légitime."
        )
    from backend.app.core.access_control import access_domain_clause
    from backend.app.models.user import User
    user = db.get(User, user_id)
    has_access, clause = access_domain_clause(db, Course, user, operation)
    if not has_access:
        raise HTTPException(status_code=403, detail=f"Droit « {operation} » refusé sur courses.")
    # clause None = droit total (au moins une ligne ir_model_access sans domaine) ; non-None =
    # restreint à un sous-ensemble, incompatible avec une action globale.
    if operation != "read" and clause is not None:
        raise HTTPException(
            status_code=403,
            detail="Cette action porte sur l'ensemble des cours, or votre droit d'écriture est "
                   "restreint à une partie d'entre eux.",
        )

# GET "" (collation teachers/classrooms/divisions/timeslots/courses/non_teaching_staffs en un
# round-trip) a été retiré : le frontend appelle désormais directement l'API générique pour
# chacune de ces ressources (voir App.vue::loadData, architecture.md §15.U) — même filtre
# school_id, mêmes données (en mieux : sqla_to_dict() sérialise plus de champs que les dicts à la
# main que cet endpoint construisait ici). Le seul filtre non trivial (timeslots "actifs") est
# désormais une hybrid_property générique (Timeslot.active, voir timeslot.py) plutôt qu'une
# logique bespoke à cet endpoint.

@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    return SolverState.get_snapshot(db_registry.slug_for_session(db))

from backend.app.solver.solver import explain_timetable_score, calculate_course_heatmap

@router.get("/score")
def get_score(school_id: Optional[int] = None, db: Session = Depends(get_db)):
    _require_course_access(db, "read")
    return explain_timetable_score(db, school_id)

@router.get("/courses/{course_id}/heatmap")
def get_course_heatmap(course_id: int, school_id: Optional[int] = None, db: Session = Depends(get_db)):
    _require_course_access(db, "read")
    return calculate_course_heatmap(db, course_id, school_id)

@router.post("/stop")
def stop_solve(db: Session = Depends(get_db)):
    _require_course_access(db, "write")
    SolverState.stop_solving(db_registry.slug_for_session(db))
    # Annule aussi bien une résolution encore en file d'attente qu'une résolution déjà en cours
    # (voir SolverState.stop_solving) — message générique pour les deux cas. Vaut aussi pour les
    # 3 nouveaux points d'entrée ci-dessous et pour le pipeline /optimize (voir
    # SolverState.stop_solving/is_stop_requested, plan salles §4, cas limite documenté dans
    # solver.py::_run_job_phases).
    return {"status": "success", "message": "Résolution annulée."}

@router.post("/course-placement")
def course_placement(school_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Endpoint 2 (plan salles §4) — remplace « Générer » : résout uniquement timeslot/week_type
    (domaine COURSE_PLACEMENT), s'arrête dès la 1ère solution faisable."""
    _require_course_access(db, "write")
    start_course_placement_async(school_id, slug=db_registry.slug_for_session(db))
    return {"status": "success", "message": "Placement automatique demandé."}

@router.post("/classroom-assignment")
def classroom_assignment(school_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Endpoint 3 (plan salles §4) — « Attribuer les salles » : résout la salle précise (domaine
    CLASSROOM_ASSIGNMENT) sur tous les cours porteurs d'une exigence de groupe."""
    _require_course_access(db, "write")
    start_classroom_assignment_async(school_id, slug=db_registry.slug_for_session(db))
    return {"status": "success", "message": "Attribution des salles demandée."}

@router.post("/reset")
def reset(db: Session = Depends(get_db)):
    _require_course_access(db, "write")
    courses = db.execute(select(Course)).scalars().unique().all()
    for c in courses:
        c.update(db, {
            "timeslot_id": None,
            "is_pinned": False
        })
    return {"status": "success"}


from pydantic import BaseModel

# Endpoint 4a/4b (« Optimiser l'emploi du temps », plan salles §4/§5) : pas de route REST ici —
# porté par WizardOptimizeTimetable (backend/app/models/wizard_optimize_timetable.py, TransientModel
# singleton) + GenericWizard.vue via l'appel de méthode d'instance générique existant
# (/api/generic/wizard_optimize_timetables/1/call/rpc_start_optimize), même mécanisme que
# WizardCourseGeneration pour « Générer les cours » — pas de nouvelle route ni de nouveau widget.


class CourseUpdate(BaseModel):
    timeslot_id: Optional[int] = None
    is_pinned: Optional[bool] = None
    # Collection possédée (commandes façon Odoo, voir CRUDMixin._apply_owned_collection_commands)
    # : id nu à conserver, ou {"classroom_id": X, "quantity": N} à créer — pas une simple liste
    # d'ids de salle depuis le retrait de course_classrooms (M2M) au profit de
    # CourseClassroomRequirement (quantity).
    classroom_requirement_ids: Optional[list] = None
    week_type: Optional[str] = None

@router.put("/courses/{course_id}")
def update_course(course_id: int, payload: CourseUpdate, db: Session = Depends(get_db)):
    # Course.read() (pas db.get()) : applique le filtre de lecture du moteur de droits — un cours
    # hors du domaine de l'utilisateur doit rester invisible (404), pas juste refuser l'écriture
    # après avoir déjà révélé son existence/état via la sérialisation plus bas.
    items = Course.read(db, domain={"id": course_id})
    course = items[0] if items else None
    if not course:
        raise HTTPException(status_code=404, detail="Cours non trouvé")
    
    vals = payload.model_dump(exclude_unset=True)
    if vals:
        try:
            course.update(db, vals)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        
    modified_courses = [course] + list(course.children)
    
    serialized_courses = [
        {
            "id": c.id,
            "subject": c.subject_relation.short_name if c.subject_relation else "Cours",
            "color": c.subject_relation.color if c.subject_relation else "#cbd5e1",
            "teacher_ids": [t.id for t in c.teachers],
            "non_teaching_staff_ids": [s.id for s in c.non_teaching_staffs],
            "division_ids": [d.id for d in c.divisions],
            "timeslot_id": c.timeslot_id,
            "classroom_requirement_ids": [{"id": r.id, "classroom_id": r.classroom_id, "quantity": r.quantity} for r in c.classroom_requirements],
            "group_ids": [g.id for g in c.groups],
            "is_pinned": c.is_pinned,
            "duration_minutes": c.duration_minutes,
            "week_type": c.week_type.value,
            "parent_id": c.parent_id,
            "status": c.status,
            "decomposition_status": c.decomposition_status,
        }
        for c in modified_courses
    ]
    
    return {"status": "success", "courses": serialized_courses}


@router.post("/structures/simulate-change")
def simulate_change(request_data: Dict[str, Any], db: Session = Depends(get_db)):
    _require_course_access(db, "read")
    action = request_data.get("action")
    resource_type = request_data.get("resource_type")
    resource_id = request_data.get("resource_id")

    impacted = []

    if action == "DELETE_RESOURCE" or action == "UPDATE_GROUP_PARTITION":
        courses_query = select(Course)
        if resource_type == "Teacher":
            courses_query = courses_query.filter(Course.teachers.any(Teacher.id == resource_id))
        elif resource_type == "NonTeachingStaff":
            courses_query = courses_query.filter(Course.non_teaching_staffs.any(NonTeachingStaff.id == resource_id))
        elif resource_type == "Classroom":
            courses_query = courses_query.filter(Course.classroom_requirements.any(CourseClassroomRequirement.classroom_id == resource_id))
        elif resource_type == "Division":
            courses_query = courses_query.filter(Course.divisions.any(Division.id == resource_id))
        elif resource_type == "Group":
            courses_query = courses_query.filter(Course.groups.any(Group.id == resource_id))
        else:
            return {
                "can_proceed": True,
                "impacted_sessions_count": 0,
                "impacted_sessions": []
            }

        # Filtre de lecture du moteur de droits (voir base.py::CRUDMixin._apply_access_read_filter)
        # — cette requête n'exécute jamais Course.read(), donc aucune protection automatique.
        courses_query = Course._apply_access_read_filter(db, courses_query)
        courses = db.execute(courses_query).scalars().unique().all()
        for c in courses:
            if c.timeslot_id is not None:
                ts = db.get(Timeslot, c.timeslot_id)
                ts_str = f"Jour {ts.day_of_week} à {ts.minutes_from_midnight // 60}h{ts.minutes_from_midnight % 60:02d}" if ts else "Créneau Inconnu"
                
                t_name = c.teachers[0].display_name if c.teachers else "Sans Prof"
                d_name = c.divisions[0].name if c.divisions else "Sans Division"
                
                impacted.append({
                    "session_id": c.id,
                    "course_label": f"{c.subject_relation.short_name if c.subject_relation else 'Cours'} - {t_name} - {d_name}",
                    "timeslot": ts_str,
                    "reason": f"Modification ou suppression de la structure de {resource_type} associée"
                })
                
    return {
        "can_proceed": True,
        "impacted_sessions_count": len(impacted),
        "impacted_sessions": impacted
    }


@router.post("/structures/apply-change")
def apply_change(request_data: Dict[str, Any], db: Session = Depends(get_db)):
    _require_course_access(db, "write")
    action = request_data.get("action")
    resource_type = request_data.get("resource_type")
    resource_id = request_data.get("resource_id")

    deplaced_count = 0

    courses_query = select(Course)
    if resource_type == "Teacher":
        courses_query = courses_query.filter(Course.teachers.any(Teacher.id == resource_id))
    elif resource_type == "Classroom":
        courses_query = courses_query.filter(Course.classroom_requirements.any(CourseClassroomRequirement.classroom_id == resource_id))
    elif resource_type == "Division":
        courses_query = courses_query.filter(Course.divisions.any(Division.id == resource_id))
    elif resource_type == "Group":
        courses_query = courses_query.filter(Course.groups.any(Group.id == resource_id))
    else:
        return {
            "success": True,
            "deplaced_sessions_count": 0,
            "diagnostic_history_id": 42
        }

    # Filtre de lecture du moteur de droits — défense en profondeur : la mutation elle-même reste
    # de toute façon protégée par c.update() (chaque cours, individuellement) ci-dessous.
    courses_query = Course._apply_access_read_filter(db, courses_query)
    courses = db.execute(courses_query).scalars().unique().all()
    for c in courses:
        if c.timeslot_id is not None:
            c.update(db, {
                "timeslot_id": None,
                "classroom_requirement_ids": []
            })
            deplaced_count += 1
            
    db.flush()
    
    return {
        "success": True,
        "deplaced_sessions_count": deplaced_count,
        "diagnostic_history_id": 42
    }

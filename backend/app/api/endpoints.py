from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.app.core.database import get_db
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.solver.solver import start_solve_timetable_async, SolverState
router = APIRouter(prefix="/api/timetable")

from typing import Dict, Any, Optional

@router.get("", response_model=Dict[str, Any])
def get_timetable(school_id: Optional[int] = None, db: Session = Depends(get_db)):
    teachers_query = db.query(Teacher)
    classrooms_query = db.query(Classroom)
    divisions_query = db.query(Division)
    courses_query = db.query(Course)
    
    if school_id is not None:
        teachers_query = teachers_query.filter(Teacher.school_id == school_id)
        classrooms_query = classrooms_query.filter(Classroom.school_id == school_id)
        divisions_query = divisions_query.filter(Division.school_id == school_id)
        courses_query = courses_query.filter(Course.school_id == school_id)
        
    teachers = teachers_query.all()
    classrooms = classrooms_query.all()
    divisions = divisions_query.all()
    timeslots = db.query(Timeslot).all()
    courses = courses_query.all()

    return {
        "teachers": [t.to_dict() if hasattr(t, "to_dict") else {"id": t.id, "name": t.name} for t in teachers],
        "classrooms": [c.to_dict() if hasattr(c, "to_dict") else {"id": c.id, "name": c.name, "capacity": c.capacity} for c in classrooms],
        "divisions": [d.to_dict() if hasattr(d, "to_dict") else {"id": d.id, "name": d.name} for d in divisions],
        "timeslots": [ts.to_dict() if hasattr(ts, "to_dict") else {"id": ts.id, "day_of_week": ts.day_of_week, "hour": ts.hour} for ts in timeslots],
        "courses": [
            {
                "id": c.id,
                "subject": c.subject,
                "teacher_id": c.teacher_id,
                "division_id": c.division_id,
                "timeslot_id": c.timeslot_id,
                "classroom_id": c.classroom_id,
                "is_pinned": c.is_pinned,
            }
            for c in courses
        ],
    }

@router.get("/status")
def get_status():
    return {"status": SolverState.get_status()}

from backend.app.solver.solver import explain_timetable_score

@router.get("/score")
def get_score(school_id: Optional[int] = None, db: Session = Depends(get_db)):
    return explain_timetable_score(db, school_id)

@router.post("/solve")
def solve(school_id: Optional[int] = None):
    start_solve_timetable_async(school_id)
    return {"status": "success", "message": "Résolution asynchrone démarrée."}

@router.post("/stop")
def stop_solve():
    SolverState.stop_solving()
    return {"status": "success", "message": "Résolution interrompue."}

@router.post("/reset")
def reset(db: Session = Depends(get_db)):
    courses = db.query(Course).all()
    for c in courses:
        c.timeslot_id = None
        c.classroom_id = None
        c.is_pinned = False
    db.commit()
    return {"status": "success"}


from pydantic import BaseModel
from typing import Optional

class CourseUpdate(BaseModel):
    timeslot_id: Optional[int] = None
    classroom_id: Optional[int] = None
    is_pinned: Optional[bool] = None

@router.put("/courses/{course_id}")
def update_course(course_id: int, payload: CourseUpdate, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Cours non trouvé")
    
    if payload.timeslot_id is not None:
        # 1. Conflit enseignant
        if course.teacher_id:
            teacher_conflict = db.query(Course).filter(
                Course.id != course.id,
                Course.teacher_id == course.teacher_id,
                Course.timeslot_id == payload.timeslot_id
            ).first()
            if teacher_conflict:
                raise HTTPException(status_code=409, detail="Conflit : L'enseignant est déjà occupé sur ce créneau")
        
        # 2. Conflit salle
        if payload.classroom_id:
            classroom_conflict = db.query(Course).filter(
                Course.id != course.id,
                Course.classroom_id == payload.classroom_id,
                Course.timeslot_id == payload.timeslot_id
            ).first()
            if classroom_conflict:
                raise HTTPException(status_code=409, detail="Conflit : La salle est déjà occupée sur ce créneau")

        # 3. Conflit division
        if course.division_id:
            division_conflict = db.query(Course).filter(
                Course.id != course.id,
                Course.division_id == course.division_id,
                Course.timeslot_id == payload.timeslot_id
            ).first()
            if division_conflict:
                raise HTTPException(status_code=409, detail="Conflit : La division est déjà occupée sur ce créneau")

    if payload.timeslot_id is not None:
        course.timeslot_id = payload.timeslot_id
    if payload.classroom_id is not None:
        course.classroom_id = payload.classroom_id
    if payload.is_pinned is not None:
        course.is_pinned = payload.is_pinned
        
    db.commit()
    return {"status": "success", "course": {
        "id": course.id,
        "subject": course.subject,
        "teacher_id": course.teacher_id,
        "division_id": course.division_id,
        "timeslot_id": course.timeslot_id,
        "classroom_id": course.classroom_id,
        "is_pinned": course.is_pinned,
    }}


@router.post("/structures/simulate-change")
def simulate_change(request_data: Dict[str, Any], db: Session = Depends(get_db)):
    action = request_data.get("action")
    resource_type = request_data.get("resource_type")
    resource_id = request_data.get("resource_id")
    
    impacted = []
    
    if action == "DELETE_RESOURCE" or action == "UPDATE_GROUP_PARTITION":
        courses_query = db.query(Course)
        if resource_type == "Teacher":
            courses_query = courses_query.filter(Course.teacher_id == resource_id)
        elif resource_type == "Classroom":
            courses_query = courses_query.filter(Course.classroom_id == resource_id)
        elif resource_type == "Division":
            courses_query = courses_query.filter(Course.division_id == resource_id)
        elif resource_type == "Group":
            courses_query = courses_query.filter(Course.group_id == resource_id)
            
        courses = courses_query.all()
        for c in courses:
            if c.timeslot_id is not None:
                ts = db.query(Timeslot).filter(Timeslot.id == c.timeslot_id).first()
                ts_str = f"Jour {ts.day_of_week} à {ts.hour}h00" if ts else "Créneau Inconnu"
                
                t_name = c.teacher.name if c.teacher else "Sans Prof"
                d_name = c.division.name if c.division else "Sans Division"
                
                impacted.append({
                    "session_id": c.id,
                    "course_label": f"{c.subject} - {t_name} - {d_name}",
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
    action = request_data.get("action")
    resource_type = request_data.get("resource_type")
    resource_id = request_data.get("resource_id")
    
    deplaced_count = 0
    
    courses_query = db.query(Course)
    if resource_type == "Teacher":
        courses_query = courses_query.filter(Course.teacher_id == resource_id)
    elif resource_type == "Classroom":
        courses_query = courses_query.filter(Course.classroom_id == resource_id)
    elif resource_type == "Division":
        courses_query = courses_query.filter(Course.division_id == resource_id)
    elif resource_type == "Group":
        courses_query = courses_query.filter(Course.group_id == resource_id)
        
    courses = courses_query.all()
    for c in courses:
        if c.timeslot_id is not None:
            c.timeslot_id = None
            c.classroom_id = None
            deplaced_count += 1
            
    db.commit()
    
    return {
        "success": True,
        "deplaced_sessions_count": deplaced_count,
        "diagnostic_history_id": 42
    }

from pydantic import BaseModel
from typing import List
from backend.app.models.preference import ResourcePreference

class PreferenceCreate(BaseModel):
    resource_type: str
    resource_id: int
    timeslot_id: int
    preference_level: str

@router.get("/preferences", response_model=List[Dict[str, Any]])
def get_preferences(resource_type: Optional[str] = None, resource_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(ResourcePreference)
    if resource_type:
        query = query.filter(ResourcePreference.resource_type == resource_type)
    if resource_id:
        query = query.filter(ResourcePreference.resource_id == resource_id)
    prefs = query.all()
    return [{
        "id": p.id,
        "resource_type": p.resource_type,
        "resource_id": p.resource_id,
        "timeslot_id": p.timeslot_id,
        "preference_level": p.preference_level
    } for p in prefs]

@router.post("/preferences")
def create_preference(payload: PreferenceCreate, db: Session = Depends(get_db)):
    existing = db.query(ResourcePreference).filter(
        ResourcePreference.resource_type == payload.resource_type,
        ResourcePreference.resource_id == payload.resource_id,
        ResourcePreference.timeslot_id == payload.timeslot_id
    ).first()
    
    if payload.preference_level == "Neutral" or payload.preference_level == "":
        if existing:
            db.delete(existing)
            db.commit()
        return {"status": "success", "message": "Preference cleared"}
        
    if existing:
        existing.preference_level = payload.preference_level
        db.commit()
        return {"status": "success", "id": existing.id}
    
    new_pref = ResourcePreference(
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        timeslot_id=payload.timeslot_id,
        preference_level=payload.preference_level
    )
    db.add(new_pref)
    db.commit()
    db.refresh(new_pref)
    return {"status": "success", "id": new_pref.id}

@router.delete("/preferences/{pref_id}")
def delete_preference(pref_id: int, db: Session = Depends(get_db)):
    pref = db.query(ResourcePreference).filter(ResourcePreference.id == pref_id).first()
    if not pref:
        raise HTTPException(status_code=404, detail="Préférence introuvable")
    db.delete(pref)
    db.commit()
    return {"status": "success"}


from backend.app.models.subject import Subject
from backend.app.models.trmd_budget import TrmdBudget

@router.get("/trmd/{school_id}")
def get_trmd_synthesis(school_id: int, db: Session = Depends(get_db)):
    subjects = db.query(Subject).all()
    budget_summary = []
    
    for subject in subjects:
        # Trouver le budget associé à la discipline de cette matière
        budget = db.query(TrmdBudget).filter(
            TrmdBudget.school_id == school_id,
            TrmdBudget.discipline_id == subject.discipline_id
        ).first()
        
        # Calculer les heures allouées (HP) converties en ETP
        # allocated_etp = allocated_hp / 18
        allocated_etp = round(budget.allocated_hp / 18.0, 2) if budget else 0.0
        
        # Calculer les heures consommées par les cours de cette matière
        courses = db.query(Course).filter(
            Course.school_id == school_id,
            Course.subject_id == subject.id
        ).all()
        
        consumed_minutes = sum(c.duration_minutes for c in courses)
        consumed_hours = consumed_minutes / 60.0
        consumed_etp = round(consumed_hours / 18.0, 2)
        
        diff_etp = round(consumed_etp - allocated_etp, 2)
        
        if consumed_etp > allocated_etp:
            status = "OVER_BUDGET"
        elif consumed_etp < allocated_etp:
            status = "UNDER_BUDGET"
        else:
            status = "ON_BUDGET"
            
        budget_summary.append({
            "subject": {
                "id": subject.id,
                "short_label": subject.short_label,
                "long_label": subject.long_label
            },
            "allocated_etp": allocated_etp,
            "consumed_etp": consumed_etp,
            "diff_etp": diff_etp,
            "status": status
        })
        
    return {
        "school_id": school_id,
        "budget_summary": budget_summary
    }


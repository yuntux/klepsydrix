from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from backend.app.core.database import get_db
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.models.non_teaching_staff import NonTeachingStaff
from backend.app.solver.solver import start_solve_timetable_async, SolverState

router = APIRouter(prefix="/api/timetable")

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
    non_teaching_staffs = db.query(NonTeachingStaff).all()

    return {
        "teachers": [t.to_dict() if hasattr(t, "to_dict") else {"id": t.id, "name": t.name, "school_id": t.school_id} for t in teachers],
        "non_teaching_staffs": [{"id": s.id, "first_name": s.first_name, "last_name": s.last_name, "role": s.role, "school_id": s.school_id} for s in non_teaching_staffs],
        "classrooms": [c.to_dict() if hasattr(c, "to_dict") else {"id": c.id, "name": c.name, "capacity": c.capacity, "school_id": c.school_id} for c in classrooms],
        "divisions": [d.to_dict() if hasattr(d, "to_dict") else {"id": d.id, "name": d.name, "school_id": d.school_id} for d in divisions],
        "timeslots": [ts.to_dict() if hasattr(ts, "to_dict") else {"id": ts.id, "day_of_week": ts.day_of_week, "hour": ts.hour} for ts in timeslots],
        "courses": [
            {
                "id": c.id,
                "subject": c.subject,
                "teacher_ids": [t.id for t in c.teachers],
                "non_teaching_staff_ids": [s.id for s in c.non_teaching_staffs],
                "division_ids": [d.id for d in c.divisions],
                "timeslot_id": c.timeslot_id,
                "classroom_ids": [cr.id for cr in c.classrooms],
                "group_ids": [g.id for g in c.groups],
                "is_pinned": c.is_pinned,
                "duration_minutes": c.duration_minutes,
                "week_type": c.effective_week_type,
                "parent_id": c.parent_id,
                "status": c.status,
                "decomposition_status": c.decomposition_status,
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
        c.update(db, {
            "timeslot_id": None,
            "is_pinned": False
        })
    return {"status": "success"}


from pydantic import BaseModel

class CourseUpdate(BaseModel):
    timeslot_id: Optional[int] = None
    is_pinned: Optional[bool] = None
    classroom_ids: Optional[list[int]] = None

@router.put("/courses/{course_id}")
def update_course(course_id: int, payload: CourseUpdate, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
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
            "subject": c.subject,
            "teacher_ids": [t.id for t in c.teachers],
            "non_teaching_staff_ids": [s.id for s in c.non_teaching_staffs],
            "division_ids": [d.id for d in c.divisions],
            "timeslot_id": c.timeslot_id,
            "classroom_ids": [cr.id for cr in c.classrooms],
            "group_ids": [g.id for g in c.groups],
            "is_pinned": c.is_pinned,
            "duration_minutes": c.duration_minutes,
            "week_type": c.effective_week_type,
            "parent_id": c.parent_id,
            "status": c.status,
            "decomposition_status": c.decomposition_status,
        }
        for c in modified_courses
    ]
    
    return {"status": "success", "courses": serialized_courses}


@router.post("/structures/simulate-change")
def simulate_change(request_data: Dict[str, Any], db: Session = Depends(get_db)):
    action = request_data.get("action")
    resource_type = request_data.get("resource_type")
    resource_id = request_data.get("resource_id")
    
    impacted = []
    
    if action == "DELETE_RESOURCE" or action == "UPDATE_GROUP_PARTITION":
        courses_query = db.query(Course)
        if resource_type == "Teacher":
            courses_query = courses_query.filter(Course.teachers.any(Teacher.id == resource_id))
        elif resource_type == "NonTeachingStaff":
            courses_query = courses_query.filter(Course.non_teaching_staffs.any(NonTeachingStaff.id == resource_id))
        elif resource_type == "Classroom":
            courses_query = courses_query.filter(Course.classrooms.any(Classroom.id == resource_id))
        elif resource_type == "Division":
            courses_query = courses_query.filter(Course.divisions.any(Division.id == resource_id))
        elif resource_type == "Group":
            courses_query = courses_query.filter(Course.groups.any(Group.id == resource_id))
            
        courses = courses_query.all()
        for c in courses:
            if c.timeslot_id is not None:
                ts = db.query(Timeslot).filter(Timeslot.id == c.timeslot_id).first()
                ts_str = f"Jour {ts.day_of_week} à {ts.hour}h00" if ts else "Créneau Inconnu"
                
                t_name = c.teachers[0].name if c.teachers else "Sans Prof"
                d_name = c.divisions[0].name if c.divisions else "Sans Division"
                
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
        courses_query = courses_query.filter(Course.teachers.any(Teacher.id == resource_id))
    elif resource_type == "Classroom":
        courses_query = courses_query.filter(Course.classrooms.any(Classroom.id == resource_id))
    elif resource_type == "Division":
        courses_query = courses_query.filter(Course.divisions.any(Division.id == resource_id))
    elif resource_type == "Group":
        courses_query = courses_query.filter(Course.groups.any(Group.id == resource_id))
        
    courses = courses_query.all()
    for c in courses:
        if c.timeslot_id is not None:
            c.update(db, {
                "timeslot_id": None,
                "classroom_ids": []
            })
            deplaced_count += 1
            
    db.flush()
    
    return {
        "success": True,
        "deplaced_sessions_count": deplaced_count,
        "diagnostic_history_id": 42
    }

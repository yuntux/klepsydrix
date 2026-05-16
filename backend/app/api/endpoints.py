from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.app.core.database import get_db
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course
from backend.app.solver.solver import solve_timetable, UnsolvableTimetableException

router = APIRouter(prefix="/api/timetable")

@router.get("", response_model=Dict[str, Any])
def get_timetable(db: Session = Depends(get_db)):
    teachers = db.query(Teacher).all()
    classrooms = db.query(Classroom).all()
    divisions = db.query(Division).all()
    timeslots = db.query(Timeslot).all()
    courses = db.query(Course).all()

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
            }
            for c in courses
        ],
    }

@router.post("/solve")
def solve(db: Session = Depends(get_db)):
    try:
        solve_timetable(db)
    except UnsolvableTimetableException as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    courses = db.query(Course).all()
    return {
        "status": "success",
        "courses": [
            {
                "id": c.id,
                "subject": c.subject,
                "teacher_id": c.teacher_id,
                "division_id": c.division_id,
                "timeslot_id": c.timeslot_id,
                "classroom_id": c.classroom_id,
            }
            for c in courses
        ]
    }

@router.post("/reset")
def reset(db: Session = Depends(get_db)):
    courses = db.query(Course).all()
    for c in courses:
        c.timeslot_id = None
        c.classroom_id = None
    db.commit()
    return {"status": "success"}


from pydantic import BaseModel
from typing import Optional

class CourseUpdate(BaseModel):
    timeslot_id: Optional[int] = None
    classroom_id: Optional[int] = None

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

    course.timeslot_id = payload.timeslot_id
    course.classroom_id = payload.classroom_id
    db.commit()
    return {"status": "success", "course": {
        "id": course.id,
        "subject": course.subject,
        "teacher_id": course.teacher_id,
        "division_id": course.division_id,
        "timeslot_id": course.timeslot_id,
        "classroom_id": course.classroom_id,
    }}


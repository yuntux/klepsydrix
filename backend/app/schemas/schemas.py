from pydantic import BaseModel, Field
from typing import List, Optional


# --- SCHÉMAS DE BASE POUR LES MODÈLES DE DONNÉES ---

class TeacherSchema(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class ClassroomSchema(BaseModel):
    id: int
    name: str
    capacity: int

    model_config = {"from_attributes": True}


class DivisionSchema(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class TimeslotSchema(BaseModel):
    id: int
    day_of_week: int = Field(..., ge=1, le=6, description="1=Lundi, 6=Samedi")
    hour: int = Field(..., ge=8, le=17, description="Créneau horaire de 8 à 17")

    model_config = {"from_attributes": True}


class CourseSchema(BaseModel):
    id: int
    subject: str
    teacher_id: int
    division_id: int
    classroom_id: Optional[int] = None
    timeslot_id: Optional[int] = None
    is_pinned: bool = False

    model_config = {"from_attributes": True}


# --- SYNC / INITIAL STATE SCHEMAS ---

class TimetableSchema(BaseModel):
    teachers: List[TeacherSchema]
    classrooms: List[ClassroomSchema]
    divisions: List[DivisionSchema]
    timeslots: List[TimeslotSchema]
    courses: List[CourseSchema]


# --- SOLVER / INPUTS & OUTPUTS ---

class SolveResultSchema(BaseModel):
    status: str = Field("success", description="success ou error")
    message: str
    courses: List[CourseSchema]


# --- MANUAL PLANIFICATION OVERRIDE ---

class ManualCourseUpdateSchema(BaseModel):
    timeslot_id: Optional[int] = None
    classroom_id: Optional[int] = None
    is_pinned: Optional[bool] = None

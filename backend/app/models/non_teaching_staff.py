from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class NonTeachingStaff(Base):
    __tablename__ = "non_teaching_staffs"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(50), nullable=False, info={"label": "Prénom", "placeholder": "ex: Jean"})
    last_name = Column(String(50), nullable=False, info={"label": "Nom de famille", "placeholder": "ex: Dupont"})
    role = Column(String(100), nullable=False, info={"label": "Rôle / Fonction", "placeholder": "ex: AESH"})
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})

    courses = relationship("Course", secondary="course_non_teaching_staffs", back_populates="non_teaching_staffs", passive_deletes="all")

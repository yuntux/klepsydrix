from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class NonTeachingStaff(Base):
    __tablename__ = "non_teaching_staffs"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    role = Column(String(100), nullable=False)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)

    courses = relationship("Course", secondary="course_non_teaching_staffs", back_populates="non_teaching_staffs", passive_deletes="all")

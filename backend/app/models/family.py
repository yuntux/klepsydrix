from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Family(Base):
    __tablename__ = "families"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    resource_type = Column(String(20), nullable=False) # 'Subject', 'Course', 'Teacher', 'Classroom'

    # Relations de navigation
    subjects = relationship("Subject", back_populates="family")
    courses = relationship("Course", back_populates="family")

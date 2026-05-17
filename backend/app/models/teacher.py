from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False)
    first_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False) # ex: 'M. Martin' (compatibilité V1)
    max_weekly_hours = Column(Float, nullable=False, default=18.0)
    
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)

    # Relations de navigation
    school = relationship("School", back_populates="teachers")
    courses = relationship("Course", back_populates="teacher", passive_deletes="all")
    # Noter que l'association avec les sessions se fait via session_teachers (Many-to-Many)

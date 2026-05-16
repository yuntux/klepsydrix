from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Classroom(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)
    capacity = Column(Integer, nullable=False, default=35)

    # Relation avec les cours accueillis dans la salle
    courses = relationship("Course", back_populates="classroom", passive_deletes="all")

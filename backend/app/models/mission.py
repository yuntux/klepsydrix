from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Mission(Base):
    __tablename__ = "missions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    hours_allowance = Column(Float, nullable=False, default=0.0)

    # Relations de navigation
    courses = relationship("Course", back_populates="mission")

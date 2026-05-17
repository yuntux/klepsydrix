from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class ElectionMethod(Base):
    __tablename__ = "election_methods"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    export_code = Column(String(20), nullable=False)

    # Relations de navigation
    courses = relationship("Course", back_populates="election_method")

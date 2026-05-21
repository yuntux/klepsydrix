from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Classroom(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False)
    name = Column(String(50), nullable=False)
    capacity = Column(Integer, nullable=False, default=35)
    quantity = Column(Integer, nullable=False, default=1) # > 1 = groupe de salles
    
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)

    # Relations de navigation
    school = relationship("School", back_populates="classrooms")
    site = relationship("Site", back_populates="classrooms")


from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Division(Base):
    __tablename__ = "divisions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False)
    name = Column(String(50), nullable=False)
    student_count = Column(Integer, nullable=False, default=0)
    color = Column(String(7), nullable=False, default="#CCCCCC")

    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    mef_id = Column(Integer, ForeignKey("mefs.id", ondelete="SET NULL"), nullable=True)

    # Relations de navigation
    school = relationship("School", back_populates="divisions")
    mef = relationship("Mef", back_populates="divisions")
    partitions = relationship("Partition", back_populates="division", passive_deletes="all")
    class_parts = relationship("ClassPart", back_populates="division", passive_deletes="all")
    courses = relationship("Course", back_populates="division", passive_deletes="all")

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class ElectionMethod(Base):
    __tablename__ = "election_methods"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de la méthode", "placeholder": "ex: STS"})
    name = Column(String(100), nullable=False, info={"label": "Nom de la méthode", "placeholder": "ex: STSWEB"})
    export_code = Column(String(20), nullable=False, info={"label": "Code d'export"})

    # Relations de navigation
    courses = relationship("Course", back_populates="election_method")

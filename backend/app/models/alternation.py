from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Alternation(Base):
    __tablename__ = "alternations"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    color = Column(String(7), nullable=True)

    # Relations de navigation
    # Les préférences et contraintes se lient via des tables associatives Many-to-Many

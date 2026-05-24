from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, index=True, nullable=False, info={"label": "Code du matériel", "placeholder": "ex: IPAD"})
    name = Column(String(100), nullable=False, info={"label": "Nom du matériel", "placeholder": "ex: Valise iPad Pro"})
    quantity = Column(Integer, nullable=False, default=1, info={"label": "Quantité disponible", "min": 1, "max": 500})

    # Relations de navigation
    # Noter que l'association avec les sessions se fait via session_materials (Many-to-Many)

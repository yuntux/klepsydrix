from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class ElectionMethod(Base):
    __tablename__ = "election_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de la méthode", "placeholder": "ex: STS"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom de la méthode", "placeholder": "ex: STSWEB"})
    export_code: Mapped[str] = mapped_column(String(20), nullable=False, info={"label": "Code d'export"})

    # Relations de navigation
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="election_method", info={"label": "Cours"})

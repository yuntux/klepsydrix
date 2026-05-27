from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Classroom(Base):
    __tablename__ = "classrooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False, info={"label": "Code de la salle", "placeholder": "ex: S101"})
    name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom de la salle", "placeholder": "ex: Salle 101"})
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=35, info={"label": "Capacité de places", "min": 1, "max": 200})
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, info={"label": "Quantité", "min": 1, "max": 10}) # > 1 = groupe de salles
    
    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, info={"label": "Site / Bâtiment"})

    # Relations de navigation
    school: Mapped[Optional["School"]] = relationship("School", back_populates="classrooms")
    site: Mapped[Optional["Site"]] = relationship("Site", back_populates="classrooms")


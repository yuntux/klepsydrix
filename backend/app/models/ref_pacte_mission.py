from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefPacteMission(Base):
    __tablename__ = "ref_pacte_missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Code"})
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, info={"label": "Mission Pacte"})
    long_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, info={"label": "Intitulé long"})

    # Course.mission_id pointe désormais ici (voir architecture.md) — l'ancien modèle Mission,
    # dédié, a été supprimé au profit de ce référentiel déjà existant.
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="mission", info={"label": "Cours"})

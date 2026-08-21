from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefAcademie(Base):
    """
    Académie de rattachement d'un établissement — `PARAMETRES/UAJ/ACADEMIE` du flux STS.

    Référentiel alimenté **à la demande** : l'import crée la ligne si le code reçu n'existe pas
    encore, plutôt que de partir d'une nomenclature figée. Une base ne connaît en pratique qu'une
    académie, parfois deux pour un établissement à cheval — inutile d'en seeder trente.
    """
    __tablename__ = "ref_academies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code", "placeholder": "ex: 01"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Académie", "placeholder": "ex: PARIS"})

    # Relations de navigation
    schools: Mapped[list["School"]] = relationship("School", back_populates="academie", passive_deletes="all", info={"label": "Établissements"})

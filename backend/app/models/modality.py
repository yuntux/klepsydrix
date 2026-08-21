from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class Modality(Base):
    """
    Modalité de cours, issue de la Base Académique des Nomenclatures : cours général, travaux
    dirigés, travaux pratiques, atelier… C'est le `CODE_MOD_COURS` porté par chaque `SERVICE` du
    flux STS.

    Donnée de référence nationale, présente dans toutes les bases de production : seedée par
    init_db.py et non par init_demo.py, au même titre que RefGrade.

    À ne pas confondre avec RefServiceMode (« modalité de service »), qui qualifie le service de
    l'enseignant et non le type d'enseignement dispensé.
    """
    __tablename__ = "modalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(4), unique=True, index=True, nullable=False, info={"label": "Code", "placeholder": "ex: CG"})
    name: Mapped[str] = mapped_column(String(30), nullable=False, info={"label": "Libellé court", "placeholder": "ex: COURS"})
    long_name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Libellé long", "placeholder": "ex: COURS GENERAL"})

    # Relations de navigation
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="modality", passive_deletes="all", info={"label": "Cours"})

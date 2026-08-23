from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefRegime(Base):
    """Régime de restauration/hébergement d'un élève (SIECLE `CODE_REGIME`) : DP=Demi-pensionnaire,
    DI=Interne, EX=Externe. Nomenclature fermée et connue, seedée dans init_db.py — contrairement
    à RefExitReason, elle n'a pas besoin d'être complétée dynamiquement à l'import."""

    __tablename__ = "ref_regimes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Régime"})

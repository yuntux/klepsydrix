from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefAccompanimentProjectType(Base):
    """Dispositif d'accompagnement personnalisé (PPRE, PAP, PPS, PAI, ULIS...). Nomenclature
    fermée et connue, seedée dans init_db.py — même patron que RefRegime/RefLegalGuardian."""

    __tablename__ = "ref_accompaniment_project_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Dispositif"})

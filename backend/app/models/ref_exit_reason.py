from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefExitReason(Base):
    """Motif de sortie d'un élève (SIECLE `CODE_MOTIF_SORTIE`). Table volontairement vide au
    départ : le code n'a pas de nomenclature fermée connue, l'import crée la ligne manquante
    plutôt que de perdre l'information, comme RefFunction/RefLevel pour les enseignants."""

    __tablename__ = "ref_exit_reasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False, info={"label": "Code"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Motif de sortie"})

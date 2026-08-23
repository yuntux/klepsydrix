from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefJob(Base):
    """Profession d'un responsable (SIECLE `CODE_PROFESSION`). Table volontairement vide au
    départ : la nomenclature n'est pas fermée, l'import crée la ligne manquante plutôt que de
    perdre l'information."""

    __tablename__ = "ref_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False, info={"label": "Code"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Profession"})

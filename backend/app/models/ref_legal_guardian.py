from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefLegalGuardian(Base):
    """Rôle de responsabilité légale (SIECLE `RESP_LEGAL`) : 0=Autre, 1=Responsable légal 1,
    2=Responsable légal 2. Nomenclature fermée et connue, seedée dans init_db.py."""

    __tablename__ = "ref_legal_guardians"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Responsabilité légale"})

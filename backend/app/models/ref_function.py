from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefFunction(Base):
    __tablename__ = "ref_functions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Code du flux STS (INDIVIDU/FONCTION, INDIVIDU/GRADE) : c'est LA clé d'appariement à
    # l'import, qui crée la ligne si le code est inconnu plutôt que de perdre l'information.
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False, info={"label": "Code"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, info={"label": "Fonction"})

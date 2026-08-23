from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefTitle(Base):
    __tablename__ = "ref_titles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, info={"label": "Civilité"})
    # Code SIECLE (PERSONNE/LC_CIVILITE, ex: "M.", "MME") : ce champ n'a AUCUNE énumération fermée
    # côté SIECLE (voir FORMATS_JUSTIFICATION.md, ResponsablesAvecAdresses §5.2 : « LC_CIVILITE n'a
    # aucune énumération »), donc pas de garantie qu'il coïncide toujours avec l'une des deux lignes
    # seedées (Monsieur/Madame) — nullable, et l'import ne le crée pas dynamiquement (contrairement
    # à RefJob/RefRelativeLink/RefExitReason) : une civilité inconnue est laissée de côté, pas
    # inventée.
    code: Mapped[Optional[str]] = mapped_column(String(10), unique=True, nullable=True, info={"label": "Code"})

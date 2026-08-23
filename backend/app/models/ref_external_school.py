from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, ForeignKey
from backend.app.models.base import Base


class RefExternalSchool(Base):
    """
    Établissement d'origine d'un élève (SIECLE `SCOLARITE_AN_DERNIER`), alimenté dynamiquement à
    l'import de la fiche élève : `name` (DENOM_PRINC) est la clé de dernier recours, `rne_code`
    (CODE_RNE) la clé préférée quand le fichier le fournit — un établissement hors académie ou à
    l'étranger peut ne pas en avoir.
    """

    __tablename__ = "ref_external_schools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, info={"label": "Autre établissement"})
    long_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, info={"label": "Dénomination complémentaire"})
    rne_code: Mapped[Optional[str]] = mapped_column(String(8), unique=True, nullable=True, info={"label": "Code UAI (RNE)"})
    sigle: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Sigle"})
    address_line1: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 1)"})
    address_line2: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 2)"})
    address_line3: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 3)"})
    address_line4: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 4)"})
    po_box: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Boîte postale"})
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Email"})
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Téléphone"})
    city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_cities.id", ondelete="SET NULL"), nullable=True, info={"label": "Commune"})

    city: Mapped[Optional["RefCity"]] = relationship("RefCity")

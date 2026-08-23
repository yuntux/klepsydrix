from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy import Integer, String, ForeignKey
from backend.app.models.base import Base, constrains


class RefCity(Base):
    __tablename__ = "ref_cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Ville"})
    country_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_countries.id", ondelete="RESTRICT"), nullable=True, info={"label": "Pays"})
    zip_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Code postal"})
    # Code officiel INSEE de la commune (SIECLE `CODE_COMMUNE_INSEE`/`CODE_COMMUNE_INSEE_NAISS`) :
    # une codification distincte du code postal, une commune pouvant avoir plusieurs codes postaux
    # et inversement. Sert de clé d'appariement pour la commune de naissance, alors que le code
    # postal + le nom servent de clé pour l'adresse (voir School._apply_school et RefCity ci-dessous).
    insee_code: Mapped[Optional[str]] = mapped_column(String(5), nullable=True, info={"label": "Code INSEE"})

    # Relations de navigation
    country: Mapped[Optional["RefCountry"]] = relationship("RefCountry")

    @constrains("name", "zip_code")
    def _check_name_zip_code_unique(self, db: Session):
        existing = db.query(RefCity).filter(
            RefCity.name == self.name,
            RefCity.zip_code == self.zip_code,
            RefCity.id != (self.id or 0),
        ).first()
        if existing:
            raise ValueError(f"Une ville « {self.name} » avec le code postal « {self.zip_code} » existe déjà.")

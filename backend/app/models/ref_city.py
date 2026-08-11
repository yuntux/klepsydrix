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

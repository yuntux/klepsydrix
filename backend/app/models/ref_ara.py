from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefAra(Base):
    __tablename__ = "ref_aras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Code"})
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, info={"label": "ARA"})
    long_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, info={"label": "Intitulé long"})

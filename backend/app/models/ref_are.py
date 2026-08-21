from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefAre(Base):
    __tablename__ = "ref_ares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False, info={"label": "Code"})
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, info={"label": "ARE"})
    long_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, info={"label": "Intitulé long"})

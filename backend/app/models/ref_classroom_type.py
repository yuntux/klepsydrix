from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String
from backend.app.models.base import Base


class RefClassroomType(Base):
    __tablename__ = "ref_classroom_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False, info={"label": "Code"})
    name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom"})
    long_name: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Libellé long"})

from typing import Optional
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.models.base import Base
from backend.app.models.user import HasUserAccount


class Parent(HasUserAccount, Base):
    __tablename__ = "parents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom"})
    first_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Prénom"})
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Email"})
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Téléphone"})
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, unique=True, info={"label": "Compte utilisateur"}
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="parent")

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

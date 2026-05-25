from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relations de navigation
    classrooms: Mapped[list["Classroom"]] = relationship("Classroom", back_populates="site")

class SiteTravelTime(Base):
    __tablename__ = "site_travel_times"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    from_site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    to_site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)

    # Relations de navigation
    from_site: Mapped[Optional["Site"]] = relationship("Site", foreign_keys=[from_site_id])
    to_site: Mapped[Optional["Site"]] = relationship("Site", foreign_keys=[to_site_id])

    __table_args__ = (
        UniqueConstraint("from_site_id", "to_site_id", name="uq_site_travel_pair"),
        CheckConstraint("from_site_id < to_site_id", name="check_travel_site_order"),
    )

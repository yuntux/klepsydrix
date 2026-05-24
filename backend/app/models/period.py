from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Period(Base):
    __tablename__ = "periods"

    id = Column(Integer, primary_key=True, index=True)
    period_type_id = Column(Integer, ForeignKey("period_types.id", ondelete="CASCADE"), nullable=False, info={"label": "Type de Période"})
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    code = Column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de la période", "placeholder": "ex: S1"})
    name = Column(String(100), nullable=False, info={"label": "Nom de la période", "placeholder": "ex: Semestre 1"})
    start_date = Column(Date, nullable=False, info={"label": "Date de début"})
    end_date = Column(Date, nullable=False, info={"label": "Date de fin"})

    # Relations de navigation
    period_type = relationship("PeriodType", back_populates="periods")
    school = relationship("School", back_populates="periods")


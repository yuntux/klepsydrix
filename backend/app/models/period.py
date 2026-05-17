from sqlalchemy import Column, Integer, String, Date
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class Period(Base):
    __tablename__ = "periods"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # Relations de navigation
    # Noter que l'association avec les préférences se fait via preference_periods (Many-to-Many)

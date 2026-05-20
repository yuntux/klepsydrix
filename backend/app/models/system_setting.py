from sqlalchemy import Column, String, Integer
from backend.app.models.base import Base

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), index=True, unique=True, nullable=False)
    value = Column(String(255), nullable=False)

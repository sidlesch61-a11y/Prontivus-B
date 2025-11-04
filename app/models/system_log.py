from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from database import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    level = Column(String(16), nullable=False, index=True)
    message = Column(Text, nullable=False)
    source = Column(String(64), nullable=False, index=True)
    details = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=True, index=True)



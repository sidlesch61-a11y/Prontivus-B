from sqlalchemy import Column, Integer, ForeignKey, DateTime, JSON, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class TissConfig(Base):
    __tablename__ = "tiss_config"
    id = Column(Integer, primary_key=True, index=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True, unique=True)

    prestador = Column(JSON, nullable=False, default=dict)
    operadora = Column(JSON, nullable=False, default=dict)
    defaults = Column(JSON, nullable=False, default=dict)
    tiss = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    clinic = relationship("Clinic")

    __table_args__ = (
        UniqueConstraint('clinic_id', name='uq_tiss_config_clinic'),
    )



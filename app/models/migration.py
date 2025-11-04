from sqlalchemy import Column, Integer, String, DateTime, JSON, Enum, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from database import Base


class MigrationType(str, enum.Enum):
    PATIENTS = "patients"
    APPOINTMENTS = "appointments"
    CLINICAL = "clinical"
    FINANCIAL = "financial"


class MigrationStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class MigrationJob(Base):
    __tablename__ = "migration_jobs"

    id = Column(Integer, primary_key=True, index=True)
    clinic_id = Column(Integer, index=True, nullable=False)
    created_by = Column(Integer, index=True, nullable=False)
    type = Column(Enum(MigrationType), nullable=False)
    status = Column(Enum(MigrationStatus), nullable=False, default=MigrationStatus.PENDING)
    input_format = Column(String(16), nullable=False)  # csv|json
    source_name = Column(String(255), nullable=True)
    params = Column(JSON, nullable=True)  # scheduling, incremental markers, options
    stats = Column(JSON, nullable=True)  # counts, durations
    errors = Column(JSON, nullable=True)  # list of error records/lines
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)



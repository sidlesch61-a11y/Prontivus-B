from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from database import Base


class FileUpload(Base):
    __tablename__ = "file_uploads"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True, nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), index=True, nullable=True)
    filename = Column(String(255), nullable=False)
    stored_path = Column(String(512), nullable=False)
    filetype = Column(String(50), nullable=False)
    upload_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Exam metadata
    exam_type = Column(String(100), nullable=True)
    exam_date = Column(DateTime(timezone=True), nullable=True)
    laboratory = Column(String(150), nullable=True)
    observations = Column(Text, nullable=True)



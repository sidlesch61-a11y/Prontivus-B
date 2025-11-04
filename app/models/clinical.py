"""
Clinical models for SOAP notes, prescriptions, and exam requests
"""
import datetime
import enum
from typing import List, Optional

from sqlalchemy import (
    Column, DateTime, Enum, ForeignKey, Integer, String, Text, Boolean, JSON
)
from sqlalchemy.orm import relationship, Mapped
from database import Base


class UrgencyLevel(enum.Enum):
    """Exam request urgency levels"""
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class ClinicalRecord(Base):
    """
    Clinical Record using SOAP format (Subjective, Objective, Assessment, Plan)
    One-to-one relationship with Appointment
    """
    __tablename__ = "clinical_records"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # SOAP Notes
    subjective = Column(Text, nullable=True)  # Patient's complaints and symptoms
    objective = Column(Text, nullable=True)   # Physical exam findings, vital signs
    assessment = Column(Text, nullable=True)  # Diagnosis or clinical impression
    # Keep legacy 'plan' for backward compatibility; new field 'plan_soap'
    plan = Column(Text, nullable=True)        # Legacy treatment plan
    plan_soap = Column(Text, nullable=True)   # SOAP "Plan" section
    
    # Relationships
    appointment_id = Column(Integer, ForeignKey("appointments.id"), unique=True, nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.datetime.now)
    
    # Relationships
    appointment: Mapped["Appointment"] = relationship("Appointment", back_populates="clinical_record", uselist=False)
    prescriptions: Mapped[List["Prescription"]] = relationship("Prescription", back_populates="clinical_record", cascade="all, delete-orphan")
    exam_requests: Mapped[List["ExamRequest"]] = relationship("ExamRequest", back_populates="clinical_record", cascade="all, delete-orphan")
    diagnoses: Mapped[List["Diagnosis"]] = relationship("Diagnosis", back_populates="clinical_record", cascade="all, delete-orphan")


class Prescription(Base):
    """
    Prescription for medication linked to a clinical record
    """
    __tablename__ = "prescriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    clinical_record_id = Column(Integer, ForeignKey("clinical_records.id"), nullable=False, index=True)
    
    # Medication details
    medication_name = Column(String(200), nullable=False)
    dosage = Column(String(100), nullable=False)  # e.g., "500mg", "10ml"
    frequency = Column(String(100), nullable=False)  # e.g., "3x ao dia", "8 em 8 horas"
    duration = Column(String(100), nullable=True)  # e.g., "7 dias", "2 semanas"
    instructions = Column(Text, nullable=True)  # Special instructions
    
    # Status
    issued_date = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.datetime.now)
    
    # Relationships
    clinical_record: Mapped["ClinicalRecord"] = relationship("ClinicalRecord", back_populates="prescriptions")


class ExamRequest(Base):
    """
    Medical exam/test request linked to a clinical record
    """
    __tablename__ = "exam_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    clinical_record_id = Column(Integer, ForeignKey("clinical_records.id"), nullable=False, index=True)
    
    # Exam details
    exam_type = Column(String(200), nullable=False)  # e.g., "Hemograma", "Raio-X", "Ultrassom"
    description = Column(Text, nullable=True)  # Additional details
    reason = Column(Text, nullable=True)  # Clinical indication
    urgency = Column(Enum(UrgencyLevel), default=UrgencyLevel.ROUTINE, nullable=False)
    
    # Status
    requested_date = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    completed_date = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.datetime.now)
    
    # Relationships
    clinical_record: Mapped["ClinicalRecord"] = relationship("ClinicalRecord", back_populates="exam_requests")


class DiagnosisType(enum.Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class Diagnosis(Base):
    """
    Diagnosis linked to a clinical record (ICD-10 / CID)
    """
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, index=True)
    clinical_record_id = Column(Integer, ForeignKey("clinical_records.id"), nullable=False, index=True)

    cid_code = Column(String(16), nullable=False)      # ICD-10 code
    description = Column(Text, nullable=True)
    type = Column(Enum(DiagnosisType), default=DiagnosisType.PRIMARY, nullable=False)

    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.datetime.now)

    clinical_record: Mapped["ClinicalRecord"] = relationship("ClinicalRecord", back_populates="diagnoses")


class ClinicalRecordVersion(Base):
    """
    Version history snapshots for ClinicalRecord with autosave support
    """
    __tablename__ = "clinical_record_versions"

    id = Column(Integer, primary_key=True, index=True)
    clinical_record_id = Column(Integer, ForeignKey("clinical_records.id"), nullable=False, index=True)
    author_user_id = Column(Integer, nullable=True)
    is_autosave = Column(Boolean, default=False, nullable=False)

    # Store snapshot of SOAP fields and related selections
    snapshot = Column(JSON, nullable=False)

    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)



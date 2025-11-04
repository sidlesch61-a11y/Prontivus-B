"""
CliniCore Database Models
SQLAlchemy ORM models for the healthcare management system
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Date, Text, 
    ForeignKey, Enum as SQLEnum, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from database import Base
import enum


# ==================== Enums ====================

class UserRole(str, enum.Enum):
    """User role enumeration"""
    ADMIN = "admin"
    SECRETARY = "secretary"
    DOCTOR = "doctor"
    PATIENT = "patient"


class AppointmentStatus(str, enum.Enum):
    """Appointment status enumeration"""
    SCHEDULED = "scheduled"
    CHECKED_IN = "checked_in"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Gender(str, enum.Enum):
    """Gender enumeration"""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


# ==================== Base Model ====================

class BaseModel(Base):
    """Base model with common fields"""
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ==================== Models ====================

class Clinic(BaseModel):
    """
    Clinic/Healthcare Facility Model
    Represents a healthcare clinic or facility in the system
    """
    __tablename__ = "clinics"
    
    # Basic Information
    name = Column(String(200), nullable=False, index=True)
    legal_name = Column(String(200), nullable=False)
    commercial_name = Column(String(200), nullable=True)  # Display name for commercial use
    tax_id = Column(String(20), unique=True, nullable=False, index=True)  # CNPJ/CPF in Brazil
    
    # Contact Information
    address = Column(Text, nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True, index=True)
    
    # Legacy Licensing Information (for backward compatibility)
    license_key = Column(String(100), unique=True, nullable=True, index=True)
    expiration_date = Column(Date, nullable=True)
    max_users = Column(Integer, default=10, nullable=False)
    active_modules = Column(JSON, nullable=True, default=list)  # List of enabled modules
    
    # New Licensing System (one-to-one with License via UUID)
    license_id = Column(UUID(as_uuid=True), ForeignKey("licenses.id"), nullable=True, unique=True, index=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    users = relationship("User", back_populates="clinic", cascade="all, delete-orphan")
    patients = relationship("Patient", back_populates="clinic", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="clinic", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="clinic", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="clinic", cascade="all, delete-orphan")
    stock_movements = relationship("StockMovement", back_populates="clinic", cascade="all, delete-orphan")
    stock_alerts = relationship("StockAlert", back_populates="clinic", cascade="all, delete-orphan")
    procedures = relationship("Procedure", back_populates="clinic", cascade="all, delete-orphan")
    insurance_plans = relationship("InsurancePlan", back_populates="clinic", cascade="all, delete-orphan")
    preauth_requests = relationship("PreAuthRequest", back_populates="clinic", cascade="all, delete-orphan")
    
    # New licensing relationships
    license = relationship(
        "License",
        uselist=False,
        foreign_keys="Clinic.license_id",
        primaryjoin="Clinic.license_id==License.id"
    )
    
    def __repr__(self):
        return f"<Clinic(id={self.id}, name='{self.name}')>"


class User(BaseModel):
    """
    User Model
    Represents system users (admin, secretary, doctor, patient)
    """
    __tablename__ = "users"
    
    # Authentication
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    
    # User Information
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.PATIENT)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # Foreign Keys
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True)
    
    # Relationships
    clinic = relationship("Clinic", back_populates="users")
    appointments_as_doctor = relationship(
        "Appointment",
        foreign_keys="Appointment.doctor_id",
        back_populates="doctor"
    )
    created_payments = relationship("Payment", back_populates="creator")
    created_preauth_requests = relationship("PreAuthRequest", back_populates="creator")
    voice_sessions = relationship("VoiceSession", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
    
    @property
    def full_name(self):
        """Get user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username


class Patient(BaseModel):
    """
    Patient Model
    Represents patients in the healthcare system
    """
    __tablename__ = "patients"
    
    # Personal Information
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    gender = Column(SQLEnum(Gender), nullable=True)
    
    # Identification
    cpf = Column(String(14), unique=True, nullable=True, index=True)  # Brazilian CPF
    
    # Contact Information
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True, index=True)
    address = Column(Text, nullable=True)
    
    # Emergency Contact
    emergency_contact_name = Column(String(100), nullable=True)
    emergency_contact_phone = Column(String(20), nullable=True)
    emergency_contact_relationship = Column(String(50), nullable=True)
    
    # Medical Information
    allergies = Column(Text, nullable=True)  # JSON or comma-separated list
    active_problems = Column(Text, nullable=True)  # Current health issues
    blood_type = Column(String(5), nullable=True)  # A+, B-, O+, etc.
    
    # Additional Notes
    notes = Column(Text, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Foreign Keys
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True)
    
    # Relationships
    clinic = relationship("Clinic", back_populates="patients")
    appointments = relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="patient", cascade="all, delete-orphan")
    preauth_requests = relationship("PreAuthRequest", back_populates="patient", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Patient(id={self.id}, name='{self.full_name}')>"
    
    @property
    def full_name(self):
        """Get patient's full name"""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        """Calculate patient's age"""
        from datetime import date
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class Appointment(BaseModel):
    """
    Appointment Model
    Represents medical appointments in the system
    """
    __tablename__ = "appointments"
    
    # Appointment Details
    scheduled_datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_minutes = Column(Integer, default=30, nullable=False)
    
    # Status and Type
    status = Column(
        SQLEnum(AppointmentStatus), 
        nullable=False, 
        default=AppointmentStatus.SCHEDULED,
        index=True
    )
    appointment_type = Column(String(100), nullable=True)  # consultation, follow-up, emergency, etc.
    
    # Notes and Observations
    notes = Column(Text, nullable=True)  # Appointment notes
    reason = Column(Text, nullable=True)  # Reason for appointment
    diagnosis = Column(Text, nullable=True)  # Doctor's diagnosis
    treatment_plan = Column(Text, nullable=True)  # Prescribed treatment
    
    # Timestamps
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    
    # Foreign Keys
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True)
    
    # Relationships
    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("User", foreign_keys=[doctor_id], back_populates="appointments_as_doctor")
    clinic = relationship("Clinic", back_populates="appointments")
    clinical_record = relationship("ClinicalRecord", back_populates="appointment", uselist=False, cascade="all, delete-orphan")
    invoice = relationship("Invoice", back_populates="appointment", uselist=False, cascade="all, delete-orphan")
    voice_sessions = relationship("VoiceSession", back_populates="appointment", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Appointment(id={self.id}, patient_id={self.patient_id}, status='{self.status}')>"
    
    @property
    def is_past(self):
        """Check if appointment is in the past"""
        from datetime import datetime, timezone
        return self.scheduled_datetime < datetime.now(timezone.utc)


# Import clinical models
from app.models.clinical import ClinicalRecord, Prescription, ExamRequest, UrgencyLevel

# Import financial models
from app.models.financial import (
    ServiceItem, Invoice, InvoiceLine, ServiceCategory, InvoiceStatus,
    Payment, PaymentMethod, PaymentStatus,
    InsurancePlan, PreAuthRequest, PreAuthStatus
)

# Import stock models
from app.models.stock import Product, StockMovement, StockAlert, ProductCategory, StockMovementType, StockMovementReason

# Import procedure models
from app.models.procedure import Procedure, ProcedureProduct

# Import licensing models
from app.models.license import License, LicenseStatus, LicensePlan
from app.models.activation import Activation, ActivationStatus
from app.models.entitlement import Entitlement, ModuleName, LimitType

# Import ICD-10 models
from app.models.icd10 import ICD10Chapter, ICD10Group, ICD10Category, ICD10Subcategory, ICD10SearchIndex

# Import voice models
from app.models.voice import VoiceSession, VoiceCommand, MedicalTerm, VoiceConfiguration

# Import patient calling models
from app.models.patient_call import PatientCall

# Import TISS template models
from app.models.tiss_template import TissTemplate, TissTemplateCategory

# Import user settings model
from app.models.user_settings import UserSettings

# Export all models
__all__ = [
    "Base",
    "BaseModel",
    "UserRole",
    "AppointmentStatus",
    "Gender",
    "UrgencyLevel",
    "ServiceCategory",
    "InvoiceStatus",
    "Clinic",
    "User",
    "Patient",
    "Appointment",
    "ClinicalRecord",
    "Prescription",
    "ExamRequest",
    "ServiceItem",
    "Invoice",
    "InvoiceLine",
    "Payment",
    "PaymentMethod",
    "PaymentStatus",
    "InsurancePlan",
    "PreAuthRequest",
    "PreAuthStatus",
    "Product",
    "StockMovement",
    "StockAlert",
    "ProductCategory",
    "StockMovementType",
    "StockMovementReason",
    "Procedure",
    "ProcedureProduct",
    "License",
    "LicenseStatus",
    "LicensePlan",
    "Activation",
    "ActivationStatus",
    "Entitlement",
    "ModuleName",
    "LimitType",
    "ICD10Chapter",
    "ICD10Group",
    "ICD10Category",
    "ICD10Subcategory",
    "ICD10SearchIndex",
    "VoiceSession",
    "VoiceCommand",
    "MedicalTerm",
    "VoiceConfiguration",
    "PatientCall",
    "TissTemplate",
    "TissTemplateCategory",
    "UserSettings",
]


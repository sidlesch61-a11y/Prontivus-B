"""
Financial module database models
"""

import enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Boolean, DateTime, 
    ForeignKey, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from . import Base


class ServiceCategory(str, enum.Enum):
    """Service item categories"""
    CONSULTATION = "consultation"
    PROCEDURE = "procedure"
    EXAM = "exam"
    MEDICATION = "medication"
    OTHER = "other"


class InvoiceStatus(str, enum.Enum):
    """Invoice status enumeration"""
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    CANCELLED = "cancelled"


class ServiceItem(Base):
    """Billable service items (procedures, consultations, etc.)"""
    __tablename__ = "service_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    code = Column(String(50), nullable=True, index=True)  # TUSS code
    price = Column(Numeric(10, 2), nullable=False)
    category = Column(SQLEnum(ServiceCategory), nullable=False, default=ServiceCategory.OTHER)
    is_active = Column(Boolean, default=True, nullable=False)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    invoice_lines = relationship("InvoiceLine", back_populates="service_item")


class Invoice(Base):
    """Patient invoices"""
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False)
    issue_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    due_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(SQLEnum(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT)
    total_amount = Column(Numeric(10, 2), nullable=False, default=0.00)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    patient = relationship("Patient", back_populates="invoices")
    appointment = relationship("Appointment", back_populates="invoice")
    clinic = relationship("Clinic", back_populates="invoices")
    invoice_lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLine(Base):
    """Individual line items on an invoice"""
    __tablename__ = "invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    service_item_id = Column(Integer, ForeignKey("service_items.id"), nullable=True)  # Made nullable for procedure-only lines
    procedure_id = Column(Integer, ForeignKey("procedures.id"), nullable=True)  # Added procedure reference
    quantity = Column(Numeric(8, 2), nullable=False, default=1.00)
    unit_price = Column(Numeric(10, 2), nullable=False)
    line_total = Column(Numeric(10, 2), nullable=False)
    description = Column(String(500), nullable=True)  # Custom description for this line
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    invoice = relationship("Invoice", back_populates="invoice_lines")
    service_item = relationship("ServiceItem", back_populates="invoice_lines")
    procedure = relationship("Procedure", back_populates="invoice_lines")


class PaymentMethod(str, enum.Enum):
    """Payment method enumeration"""
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BANK_TRANSFER = "bank_transfer"
    PIX = "pix"
    CHECK = "check"
    INSURANCE = "insurance"
    OTHER = "other"


class PaymentStatus(str, enum.Enum):
    """Payment status enumeration"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Payment(Base):
    """Payment records for invoices"""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(SQLEnum(PaymentMethod), nullable=False)
    status = Column(SQLEnum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    reference_number = Column(String(100), nullable=True)  # Transaction reference
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    invoice = relationship("Invoice", back_populates="payments")
    creator = relationship("User", back_populates="created_payments")


class InsurancePlan(Base):
    """Insurance plans and coverage rules"""
    __tablename__ = "insurance_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    insurance_company = Column(String(200), nullable=False)
    ans_registration = Column(String(6), nullable=False, index=True)
    coverage_percentage = Column(Numeric(5, 2), nullable=False, default=100.00)  # Coverage percentage
    requires_preauth = Column(Boolean, default=False, nullable=False)
    max_annual_limit = Column(Numeric(10, 2), nullable=True)
    max_procedure_limit = Column(Numeric(10, 2), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    clinic = relationship("Clinic", back_populates="insurance_plans")
    preauth_requests = relationship("PreAuthRequest", back_populates="insurance_plan")


class PreAuthStatus(str, enum.Enum):
    """Pre-authorization status enumeration"""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PreAuthRequest(Base):
    """Pre-authorization requests for procedures"""
    __tablename__ = "preauth_requests"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    insurance_plan_id = Column(Integer, ForeignKey("insurance_plans.id"), nullable=False)
    procedure_code = Column(String(10), nullable=False)
    procedure_description = Column(String(200), nullable=False)
    requested_amount = Column(Numeric(10, 2), nullable=False)
    approved_amount = Column(Numeric(10, 2), nullable=True)
    status = Column(SQLEnum(PreAuthStatus), nullable=False, default=PreAuthStatus.PENDING)
    request_date = Column(DateTime(timezone=True), server_default=func.now())
    response_date = Column(DateTime(timezone=True), nullable=True)
    authorization_number = Column(String(50), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    patient = relationship("Patient", back_populates="preauth_requests")
    insurance_plan = relationship("InsurancePlan", back_populates="preauth_requests")
    clinic = relationship("Clinic", back_populates="preauth_requests")
    creator = relationship("User", back_populates="created_preauth_requests")
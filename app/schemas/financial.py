"""
Financial module Pydantic schemas
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field

from app.models import ServiceCategory, InvoiceStatus


# ==================== Service Items ====================

class ServiceItemBase(BaseModel):
    """Base service item schema"""
    name: str = Field(..., max_length=200, description="Service item name")
    description: Optional[str] = Field(None, description="Service item description")
    code: Optional[str] = Field(None, max_length=50, description="TUSS code")
    price: Decimal = Field(..., decimal_places=2, description="Service price")
    category: ServiceCategory = Field(..., description="Service category")
    is_active: bool = Field(default=True, description="Whether the service is active")


class ServiceItemCreate(ServiceItemBase):
    """Schema for creating a service item"""
    pass


class ServiceItemUpdate(BaseModel):
    """Schema for updating a service item"""
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    code: Optional[str] = Field(None, max_length=50)
    price: Optional[Decimal] = Field(None, decimal_places=2)
    category: Optional[ServiceCategory] = None
    is_active: Optional[bool] = None


class ServiceItemResponse(ServiceItemBase):
    """Schema for service item responses"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== Invoices ====================

class InvoiceLineBase(BaseModel):
    """Base invoice line schema"""
    service_item_id: Optional[int] = Field(None, description="Service item ID")
    procedure_id: Optional[int] = Field(None, description="Procedure ID")
    quantity: Decimal = Field(..., decimal_places=2, description="Quantity")
    unit_price: Decimal = Field(..., decimal_places=2, description="Unit price")
    description: Optional[str] = Field(None, max_length=500, description="Line description")


class InvoiceLineCreate(InvoiceLineBase):
    """Schema for creating an invoice line"""
    pass


class InvoiceLineResponse(InvoiceLineBase):
    """Schema for invoice line responses"""
    id: int
    line_total: Decimal
    created_at: datetime
    service_item: Optional[ServiceItemResponse] = None
    procedure_name: Optional[str] = None

    class Config:
        from_attributes = True


class InvoiceBase(BaseModel):
    """Base invoice schema"""
    patient_id: int = Field(..., description="Patient ID")
    appointment_id: Optional[int] = Field(None, description="Related appointment ID")
    due_date: Optional[datetime] = Field(None, description="Payment due date")
    notes: Optional[str] = Field(None, description="Invoice notes")


class InvoiceCreate(InvoiceBase):
    """Schema for creating an invoice"""
    service_items: List[InvoiceLineCreate] = Field(..., description="List of service items to bill")


class InvoiceUpdate(BaseModel):
    """Schema for updating an invoice"""
    due_date: Optional[datetime] = None
    status: Optional[InvoiceStatus] = None
    notes: Optional[str] = None


class InvoiceResponse(InvoiceBase):
    """Schema for invoice responses"""
    id: int
    issue_date: datetime
    status: InvoiceStatus
    total_amount: Decimal
    created_at: datetime
    updated_at: Optional[datetime] = None
    patient_name: Optional[str] = None
    appointment_date: Optional[datetime] = None
    invoice_lines: Optional[List[InvoiceLineResponse]] = None

    class Config:
        from_attributes = True


class InvoiceDetailResponse(InvoiceResponse):
    """Detailed invoice response with all relationships"""
    patient_name: str
    appointment_date: Optional[datetime] = None
    doctor_name: Optional[str] = None
    invoice_lines: List[InvoiceLineResponse]


# ==================== Invoice Generation ====================

class InvoiceFromAppointmentCreate(BaseModel):
    """Schema for creating an invoice from a completed appointment"""
    appointment_id: int = Field(..., description="Appointment ID")
    service_items: List[InvoiceLineCreate] = Field(..., description="Service items to bill")
    due_date: Optional[datetime] = Field(None, description="Payment due date")
    notes: Optional[str] = Field(None, description="Invoice notes")


# ==================== Filters ====================

class InvoiceFilters(BaseModel):
    """Schema for invoice filtering"""
    patient_id: Optional[int] = None
    status: Optional[InvoiceStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None


class ServiceItemFilters(BaseModel):
    """Schema for service item filtering"""
    category: Optional[ServiceCategory] = None
    is_active: Optional[bool] = None
    search: Optional[str] = None


# ==================== Payments ====================

class PaymentBase(BaseModel):
    """Base payment schema"""
    amount: Decimal = Field(..., decimal_places=2, description="Payment amount")
    method: str = Field(..., description="Payment method")
    reference_number: Optional[str] = Field(None, max_length=100, description="Transaction reference")
    notes: Optional[str] = Field(None, description="Payment notes")


class PaymentCreate(PaymentBase):
    """Schema for creating a payment"""
    invoice_id: int = Field(..., description="Invoice ID")


class PaymentUpdate(BaseModel):
    """Schema for updating a payment"""
    amount: Optional[Decimal] = Field(None, decimal_places=2)
    method: Optional[str] = None
    status: Optional[str] = None
    reference_number: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class PaymentResponse(PaymentBase):
    """Schema for payment responses"""
    id: int
    invoice_id: int
    status: str
    paid_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    creator_name: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== Insurance Plans ====================

class InsurancePlanBase(BaseModel):
    """Base insurance plan schema"""
    name: str = Field(..., max_length=200, description="Plan name")
    insurance_company: str = Field(..., max_length=200, description="Insurance company")
    ans_registration: str = Field(..., max_length=6, description="ANS registration number")
    coverage_percentage: Decimal = Field(..., decimal_places=2, description="Coverage percentage")
    requires_preauth: bool = Field(default=False, description="Requires pre-authorization")
    max_annual_limit: Optional[Decimal] = Field(None, decimal_places=2, description="Maximum annual limit")
    max_procedure_limit: Optional[Decimal] = Field(None, decimal_places=2, description="Maximum procedure limit")
    is_active: bool = Field(default=True, description="Whether the plan is active")


class InsurancePlanCreate(InsurancePlanBase):
    """Schema for creating an insurance plan"""
    pass


class InsurancePlanUpdate(BaseModel):
    """Schema for updating an insurance plan"""
    name: Optional[str] = Field(None, max_length=200)
    insurance_company: Optional[str] = Field(None, max_length=200)
    ans_registration: Optional[str] = Field(None, max_length=6)
    coverage_percentage: Optional[Decimal] = Field(None, decimal_places=2)
    requires_preauth: Optional[bool] = None
    max_annual_limit: Optional[Decimal] = Field(None, decimal_places=2)
    max_procedure_limit: Optional[Decimal] = Field(None, decimal_places=2)
    is_active: Optional[bool] = None


class InsurancePlanResponse(InsurancePlanBase):
    """Schema for insurance plan responses"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== Pre-Authorization ====================

class PreAuthRequestBase(BaseModel):
    """Base pre-authorization request schema"""
    procedure_code: str = Field(..., max_length=10, description="Procedure code")
    procedure_description: str = Field(..., max_length=200, description="Procedure description")
    requested_amount: Decimal = Field(..., decimal_places=2, description="Requested amount")
    notes: Optional[str] = Field(None, description="Request notes")


class PreAuthRequestCreate(PreAuthRequestBase):
    """Schema for creating a pre-authorization request"""
    patient_id: int = Field(..., description="Patient ID")
    insurance_plan_id: int = Field(..., description="Insurance plan ID")


class PreAuthRequestUpdate(BaseModel):
    """Schema for updating a pre-authorization request"""
    procedure_code: Optional[str] = Field(None, max_length=10)
    procedure_description: Optional[str] = Field(None, max_length=200)
    requested_amount: Optional[Decimal] = Field(None, decimal_places=2)
    approved_amount: Optional[Decimal] = Field(None, decimal_places=2)
    status: Optional[str] = None
    authorization_number: Optional[str] = Field(None, max_length=50)
    valid_until: Optional[datetime] = None
    notes: Optional[str] = None


class PreAuthRequestResponse(PreAuthRequestBase):
    """Schema for pre-authorization request responses"""
    id: int
    patient_id: int
    insurance_plan_id: int
    approved_amount: Optional[Decimal] = None
    status: str
    request_date: datetime
    response_date: Optional[datetime] = None
    authorization_number: Optional[str] = None
    valid_until: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    patient_name: Optional[str] = None
    insurance_plan_name: Optional[str] = None
    creator_name: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== Accounts Receivable ====================

class AccountsReceivableSummary(BaseModel):
    """Accounts receivable summary"""
    total_outstanding: Decimal = Field(..., decimal_places=2, description="Total outstanding amount")
    current: Decimal = Field(..., decimal_places=2, description="Current (0-30 days)")
    days_31_60: Decimal = Field(..., decimal_places=2, description="31-60 days")
    days_61_90: Decimal = Field(..., decimal_places=2, description="61-90 days")
    over_90_days: Decimal = Field(..., decimal_places=2, description="Over 90 days")
    total_invoices: int = Field(..., description="Total number of invoices")


class AgingReportItem(BaseModel):
    """Individual aging report item"""
    invoice_id: int
    patient_name: str
    invoice_date: datetime
    due_date: Optional[datetime] = None
    total_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    days_overdue: int
    status: str


class AgingReport(BaseModel):
    """Complete aging report"""
    summary: AccountsReceivableSummary
    items: List[AgingReportItem]
    generated_at: datetime
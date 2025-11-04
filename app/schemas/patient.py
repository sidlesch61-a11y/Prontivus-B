"""
Patient Pydantic schemas for request/response validation
"""
import datetime
from typing import Optional
from pydantic import BaseModel, Field, validator
from app.models import Gender
from app.core.validators import validate_cpf, validate_phone, validate_email, sanitize_input


class PatientBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: datetime.date
    gender: Gender
    cpf: Optional[str] = Field(None, max_length=14)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=255)
    emergency_contact_name: Optional[str] = Field(None, max_length=100)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)
    emergency_contact_relationship: Optional[str] = Field(None, max_length=50)
    allergies: Optional[str] = None
    active_problems: Optional[str] = None
    blood_type: Optional[str] = Field(None, max_length=5)
    notes: Optional[str] = None
    is_active: bool = True


class PatientCreate(PatientBase):
    clinic_id: int

    @validator('cpf')
    def validate_cpf_field(cls, v):
        if v:
            return validate_cpf(v)
        return v

    @validator('phone')
    def validate_phone_field(cls, v):
        if v:
            return validate_phone(v)
        return v

    @validator('email')
    def validate_email_field(cls, v):
        if v:
            return validate_email(v)
        return v

    @validator('first_name', 'last_name', 'emergency_contact_name')
    def sanitize_names(cls, v):
        if v:
            return sanitize_input(v, max_length=100)
        return v

    @validator('address', 'allergies', 'active_problems', 'notes')
    def sanitize_text_fields(cls, v):
        if v:
            return sanitize_input(v, max_length=1000)
        return v


class PatientUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    date_of_birth: Optional[datetime.date] = None
    gender: Optional[Gender] = None
    cpf: Optional[str] = Field(None, max_length=14)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=255)
    emergency_contact_name: Optional[str] = Field(None, max_length=100)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)
    emergency_contact_relationship: Optional[str] = Field(None, max_length=50)
    allergies: Optional[str] = None
    active_problems: Optional[str] = None
    blood_type: Optional[str] = Field(None, max_length=5)
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('cpf')
    def validate_cpf_field(cls, v):
        if v:
            return validate_cpf(v)
        return v

    @validator('phone')
    def validate_phone_field(cls, v):
        if v:
            return validate_phone(v)
        return v

    @validator('email')
    def validate_email_field(cls, v):
        if v:
            return validate_email(v)
        return v

    @validator('first_name', 'last_name', 'emergency_contact_name')
    def sanitize_names(cls, v):
        if v:
            return sanitize_input(v, max_length=100)
        return v

    @validator('address', 'allergies', 'active_problems', 'notes')
    def sanitize_text_fields(cls, v):
        if v:
            return sanitize_input(v, max_length=1000)
        return v


class PatientResponse(PatientBase):
    id: int
    clinic_id: int
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    
    class Config:
        from_attributes = True


class PatientListResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    cpf: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    date_of_birth: datetime.date
    gender: Gender
    
    class Config:
        from_attributes = True


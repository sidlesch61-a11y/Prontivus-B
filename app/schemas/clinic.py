"""
Clinic Pydantic schemas
"""

from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from app.core.licensing import AVAILABLE_MODULES, validate_module_combination


class ClinicBase(BaseModel):
    """Base clinic schema"""
    name: str = Field(..., min_length=1, max_length=200)
    legal_name: str = Field(..., min_length=1, max_length=200)
    tax_id: str = Field(..., min_length=1, max_length=20)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    is_active: bool = True


class ClinicCreate(ClinicBase):
    """Schema for creating a new clinic"""
    license_key: Optional[str] = Field(None, max_length=100)
    expiration_date: Optional[date] = None
    max_users: int = Field(10, ge=1, le=1000)
    active_modules: List[str] = Field(default_factory=list)
    
    @validator('active_modules')
    def validate_modules(cls, v):
        if not v:
            return []
        
        # Check if all modules are valid
        invalid_modules = set(v) - set(AVAILABLE_MODULES)
        if invalid_modules:
            raise ValueError(f"Invalid modules: {', '.join(invalid_modules)}")
        
        # Validate module dependencies
        try:
            validate_module_combination(v)
        except Exception as e:
            raise ValueError(str(e))
        
        return v


class ClinicUpdate(BaseModel):
    """Schema for updating a clinic"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    legal_name: Optional[str] = Field(None, min_length=1, max_length=200)
    tax_id: Optional[str] = Field(None, min_length=1, max_length=20)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    license_key: Optional[str] = Field(None, max_length=100)
    expiration_date: Optional[date] = None
    max_users: Optional[int] = Field(None, ge=1, le=1000)
    active_modules: Optional[List[str]] = None
    
    @validator('active_modules')
    def validate_modules(cls, v):
        if v is None:
            return v
        
        if not v:
            return []
        
        # Check if all modules are valid
        invalid_modules = set(v) - set(AVAILABLE_MODULES)
        if invalid_modules:
            raise ValueError(f"Invalid modules: {', '.join(invalid_modules)}")
        
        # Validate module dependencies
        try:
            validate_module_combination(v)
        except Exception as e:
            raise ValueError(str(e))
        
        return v


class ClinicResponse(ClinicBase):
    """Schema for clinic response"""
    id: int
    license_key: Optional[str] = None
    expiration_date: Optional[date] = None
    max_users: int
    active_modules: List[str] = Field(default_factory=list)
    created_at: date
    updated_at: Optional[date] = None
    
    class Config:
        from_attributes = True


class ClinicListResponse(BaseModel):
    """Schema for clinic list response"""
    id: int
    name: str
    legal_name: str
    tax_id: str
    email: Optional[str] = None
    is_active: bool
    license_key: Optional[str] = None
    expiration_date: Optional[date] = None
    max_users: int
    active_modules: List[str] = Field(default_factory=list)
    user_count: int = 0
    created_at: date
    
    class Config:
        from_attributes = True


class ClinicLicenseUpdate(BaseModel):
    """Schema for updating clinic license"""
    license_key: Optional[str] = Field(None, max_length=100)
    expiration_date: Optional[date] = None
    max_users: Optional[int] = Field(None, ge=1, le=1000)
    active_modules: Optional[List[str]] = None
    
    @validator('active_modules')
    def validate_modules(cls, v):
        if v is None:
            return v
        
        if not v:
            return []
        
        # Check if all modules are valid
        invalid_modules = set(v) - set(AVAILABLE_MODULES)
        if invalid_modules:
            raise ValueError(f"Invalid modules: {', '.join(invalid_modules)}")
        
        # Validate module dependencies
        try:
            validate_module_combination(v)
        except Exception as e:
            raise ValueError(str(e))
        
        return v


class ClinicStatsResponse(BaseModel):
    """Schema for clinic statistics"""
    total_clinics: int
    active_clinics: int
    expired_licenses: int
    total_users: int
    clinics_near_expiration: int  # Expiring in next 30 days

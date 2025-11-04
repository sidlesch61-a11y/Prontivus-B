"""
License Pydantic schemas for request/response validation
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from app.models.license import LicenseStatus, LicensePlan
from app.core.validators import sanitize_input


class LicenseBase(BaseModel):
    """Base license schema"""
    plan: LicensePlan = Field(..., description="License plan type")
    modules: List[str] = Field(default_factory=list, description="List of enabled modules")
    users_limit: int = Field(..., ge=1, description="Maximum number of users allowed")
    units_limit: Optional[int] = Field(None, ge=1, description="Maximum number of units/clinics allowed")
    start_at: datetime = Field(..., description="License start date")
    end_at: datetime = Field(..., description="License end date")
    status: LicenseStatus = Field(default=LicenseStatus.ACTIVE, description="License status")
    signature: Optional[str] = Field(None, description="License signature for validation")

    @validator('modules')
    def validate_modules(cls, v):
        """Validate modules list"""
        if not isinstance(v, list):
            raise ValueError('Modules must be a list')
        
        # Validate each module name
        valid_modules = [
            'patients', 'appointments', 'clinical', 'financial', 'stock',
            'procedures', 'tiss', 'bi', 'telemed', 'mobile', 'api',
            'reports', 'backup', 'integration'
        ]
        
        for module in v:
            if module not in valid_modules:
                raise ValueError(f'Invalid module: {module}')
        
        return v

    @validator('end_at')
    def validate_end_date(cls, v, values):
        """Validate end date is after start date"""
        if 'start_at' in values and v <= values['start_at']:
            raise ValueError('End date must be after start date')
        return v

    @validator('users_limit')
    def validate_users_limit(cls, v):
        """Validate users limit"""
        if v < 1:
            raise ValueError('Users limit must be at least 1')
        if v > 10000:
            raise ValueError('Users limit cannot exceed 10000')
        return v

    @validator('units_limit')
    def validate_units_limit(cls, v):
        """Validate units limit"""
        if v is not None and v < 1:
            raise ValueError('Units limit must be at least 1')
        return v


class LicenseCreate(LicenseBase):
    """License creation schema"""
    tenant_id: uuid.UUID = Field(..., description="Tenant (clinic) ID")


class LicenseUpdate(BaseModel):
    """License update schema"""
    plan: Optional[LicensePlan] = None
    modules: Optional[List[str]] = None
    users_limit: Optional[int] = Field(None, ge=1, le=10000)
    units_limit: Optional[int] = Field(None, ge=1)
    end_at: Optional[datetime] = None
    status: Optional[LicenseStatus] = None
    signature: Optional[str] = None

    @validator('modules')
    def validate_modules(cls, v):
        """Validate modules list"""
        if v is not None:
            valid_modules = [
                'patients', 'appointments', 'clinical', 'financial', 'stock',
                'procedures', 'tiss', 'bi', 'telemed', 'mobile', 'api',
                'reports', 'backup', 'integration'
            ]
            
            for module in v:
                if module not in valid_modules:
                    raise ValueError(f'Invalid module: {module}')
        
        return v


class LicenseResponse(LicenseBase):
    """License response schema"""
    id: uuid.UUID = Field(..., description="License ID")
    tenant_id: uuid.UUID = Field(..., description="Tenant (clinic) ID")
    activation_key: uuid.UUID = Field(..., description="License activation key")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    is_active: bool = Field(..., description="Whether license is currently active")
    is_expired: bool = Field(..., description="Whether license has expired")
    days_until_expiry: int = Field(..., description="Days until license expires")

    class Config:
        from_attributes = True


class LicenseListResponse(BaseModel):
    """License list response schema"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    plan: LicensePlan
    status: LicenseStatus
    users_limit: int
    start_at: datetime
    end_at: datetime
    is_active: bool
    is_expired: bool
    days_until_expiry: int
    created_at: datetime

    class Config:
        from_attributes = True


class LicenseSummary(BaseModel):
    """License summary schema"""
    id: uuid.UUID
    plan: LicensePlan
    status: LicenseStatus
    modules: List[str]
    users_limit: int
    is_active: bool
    days_until_expiry: int

    class Config:
        from_attributes = True


class LicenseValidation(BaseModel):
    """License validation schema"""
    activation_key: uuid.UUID = Field(..., description="License activation key")
    instance_id: str = Field(..., min_length=1, max_length=255, description="Instance identifier")
    device_info: Optional[Dict[str, Any]] = Field(None, description="Device information")

    @validator('instance_id')
    def sanitize_instance_id(cls, v):
        """Sanitize instance ID"""
        return sanitize_input(v, max_length=255)

    @validator('device_info')
    def validate_device_info(cls, v):
        """Validate device info structure"""
        if v is not None:
            # Ensure device_info is a dictionary
            if not isinstance(v, dict):
                raise ValueError('Device info must be a dictionary')
            
            # Validate common device info fields
            allowed_fields = [
                'fingerprint', 'os_info', 'browser_info', 'ip_address',
                'user_agent', 'screen_resolution', 'timezone'
            ]
            
            for key in v.keys():
                if key not in allowed_fields:
                    raise ValueError(f'Invalid device info field: {key}')
        
        return v


class LicenseActivationRequest(BaseModel):
    """License activation request schema"""
    activation_key: uuid.UUID = Field(..., description="License activation key")
    instance_id: str = Field(..., min_length=1, max_length=255, description="Instance identifier")
    device_info: Optional[Dict[str, Any]] = Field(None, description="Device information")
    tenant_info: Optional[Dict[str, Any]] = Field(None, description="Tenant information")

    @validator('instance_id')
    def sanitize_instance_id(cls, v):
        """Sanitize instance ID"""
        return sanitize_input(v, max_length=255)

    @validator('device_info', 'tenant_info')
    def validate_info_dict(cls, v):
        """Validate info dictionaries"""
        if v is not None and not isinstance(v, dict):
            raise ValueError('Info must be a dictionary')
        return v


class LicenseActivationResponse(BaseModel):
    """License activation response schema"""
    success: bool = Field(..., description="Whether activation was successful")
    message: str = Field(..., description="Activation message")
    license_id: Optional[uuid.UUID] = Field(None, description="Activated license ID")
    activation_id: Optional[uuid.UUID] = Field(None, description="Activation record ID")
    expires_at: Optional[datetime] = Field(None, description="License expiration date")
    modules: Optional[List[str]] = Field(None, description="Enabled modules")


class LicenseStatusUpdate(BaseModel):
    """License status update schema"""
    status: LicenseStatus = Field(..., description="New license status")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for status change")

    @validator('reason')
    def sanitize_reason(cls, v):
        """Sanitize reason text"""
        if v:
            return sanitize_input(v, max_length=500)
        return v


"""
Activation Pydantic schemas for request/response validation
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from app.models.activation import ActivationStatus
from app.core.validators import sanitize_input


class ActivationBase(BaseModel):
    """Base activation schema"""
    instance_id: str = Field(..., min_length=1, max_length=255, description="Instance identifier")
    device_info: Optional[Dict[str, Any]] = Field(None, description="Device information")
    status: ActivationStatus = Field(default=ActivationStatus.ACTIVE, description="Activation status")

    @validator('instance_id')
    def sanitize_instance_id(cls, v):
        """Sanitize instance ID"""
        return sanitize_input(v, max_length=255)

    @validator('device_info')
    def validate_device_info(cls, v):
        """Validate device info structure"""
        if v is not None:
            if not isinstance(v, dict):
                raise ValueError('Device info must be a dictionary')
            
            # Validate common device info fields
            allowed_fields = [
                'fingerprint', 'os_info', 'browser_info', 'ip_address',
                'user_agent', 'screen_resolution', 'timezone', 'language',
                'platform', 'version', 'architecture'
            ]
            
            for key in v.keys():
                if key not in allowed_fields:
                    raise ValueError(f'Invalid device info field: {key}')
        
        return v


class ActivationCreate(ActivationBase):
    """Activation creation schema"""
    license_id: uuid.UUID = Field(..., description="License ID")


class ActivationUpdate(BaseModel):
    """Activation update schema"""
    device_info: Optional[Dict[str, Any]] = None
    status: Optional[ActivationStatus] = None
    last_check_at: Optional[datetime] = None

    @validator('device_info')
    def validate_device_info(cls, v):
        """Validate device info structure"""
        if v is not None:
            if not isinstance(v, dict):
                raise ValueError('Device info must be a dictionary')
            
            allowed_fields = [
                'fingerprint', 'os_info', 'browser_info', 'ip_address',
                'user_agent', 'screen_resolution', 'timezone', 'language',
                'platform', 'version', 'architecture'
            ]
            
            for key in v.keys():
                if key not in allowed_fields:
                    raise ValueError(f'Invalid device info field: {key}')
        
        return v


class ActivationResponse(ActivationBase):
    """Activation response schema"""
    id: uuid.UUID = Field(..., description="Activation ID")
    license_id: uuid.UUID = Field(..., description="License ID")
    activated_at: datetime = Field(..., description="Activation timestamp")
    last_check_at: Optional[datetime] = Field(None, description="Last check timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    is_active: bool = Field(..., description="Whether activation is currently active")
    days_since_activation: int = Field(..., description="Days since activation")
    days_since_last_check: Optional[int] = Field(None, description="Days since last check")

    class Config:
        from_attributes = True


class ActivationListResponse(BaseModel):
    """Activation list response schema"""
    id: uuid.UUID
    license_id: uuid.UUID
    instance_id: str
    status: ActivationStatus
    activated_at: datetime
    last_check_at: Optional[datetime]
    is_active: bool
    days_since_activation: int
    days_since_last_check: Optional[int]

    class Config:
        from_attributes = True


class ActivationCheckRequest(BaseModel):
    """Activation check request schema"""
    instance_id: str = Field(..., min_length=1, max_length=255, description="Instance identifier")
    device_info: Optional[Dict[str, Any]] = Field(None, description="Current device information")

    @validator('instance_id')
    def sanitize_instance_id(cls, v):
        """Sanitize instance ID"""
        return sanitize_input(v, max_length=255)

    @validator('device_info')
    def validate_device_info(cls, v):
        """Validate device info structure"""
        if v is not None:
            if not isinstance(v, dict):
                raise ValueError('Device info must be a dictionary')
        
        return v


class ActivationCheckResponse(BaseModel):
    """Activation check response schema"""
    valid: bool = Field(..., description="Whether activation is valid")
    message: str = Field(..., description="Check result message")
    activation_id: Optional[uuid.UUID] = Field(None, description="Activation ID")
    license_id: Optional[uuid.UUID] = Field(None, description="License ID")
    status: Optional[ActivationStatus] = Field(None, description="Activation status")
    requires_update: bool = Field(default=False, description="Whether device info needs update")


class ActivationRevokeRequest(BaseModel):
    """Activation revoke request schema"""
    reason: Optional[str] = Field(None, max_length=500, description="Reason for revocation")

    @validator('reason')
    def sanitize_reason(cls, v):
        """Sanitize reason text"""
        if v:
            return sanitize_input(v, max_length=500)
        return v


class ActivationMigrateRequest(BaseModel):
    """Activation migrate request schema"""
    new_instance_id: str = Field(..., min_length=1, max_length=255, description="New instance identifier")
    new_device_info: Optional[Dict[str, Any]] = Field(None, description="New device information")
    migration_reason: Optional[str] = Field(None, max_length=500, description="Migration reason")

    @validator('new_instance_id')
    def sanitize_new_instance_id(cls, v):
        """Sanitize new instance ID"""
        return sanitize_input(v, max_length=255)

    @validator('new_device_info')
    def validate_new_device_info(cls, v):
        """Validate new device info structure"""
        if v is not None:
            if not isinstance(v, dict):
                raise ValueError('Device info must be a dictionary')
        
        return v

    @validator('migration_reason')
    def sanitize_migration_reason(cls, v):
        """Sanitize migration reason"""
        if v:
            return sanitize_input(v, max_length=500)
        return v


class DeviceInfo(BaseModel):
    """Device information schema"""
    fingerprint: Optional[str] = Field(None, max_length=255, description="Device fingerprint")
    os_info: Optional[Dict[str, Any]] = Field(None, description="Operating system information")
    browser_info: Optional[Dict[str, Any]] = Field(None, description="Browser information")
    ip_address: Optional[str] = Field(None, max_length=45, description="IP address")
    user_agent: Optional[str] = Field(None, max_length=500, description="User agent string")
    screen_resolution: Optional[str] = Field(None, max_length=20, description="Screen resolution")
    timezone: Optional[str] = Field(None, max_length=50, description="Timezone")
    language: Optional[str] = Field(None, max_length=10, description="Language code")
    platform: Optional[str] = Field(None, max_length=50, description="Platform")
    version: Optional[str] = Field(None, max_length=50, description="Version")

    @validator('fingerprint', 'ip_address', 'user_agent', 'screen_resolution', 'timezone', 'language', 'platform', 'version')
    def sanitize_string_fields(cls, v):
        """Sanitize string fields"""
        if v:
            return sanitize_input(v, max_length=500)
        return v

    @validator('os_info', 'browser_info')
    def validate_info_dict(cls, v):
        """Validate info dictionaries"""
        if v is not None and not isinstance(v, dict):
            raise ValueError('Info must be a dictionary')
        return v


"""
Entitlement Pydantic schemas for request/response validation
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
from app.models.entitlement import ModuleName, LimitType
from app.core.validators import sanitize_input


class EntitlementBase(BaseModel):
    """Base entitlement schema"""
    module: str = Field(..., min_length=1, max_length=50, description="Module name")
    enabled: bool = Field(default=True, description="Whether module is enabled")
    limits_json: Optional[Dict[str, Any]] = Field(None, description="Module-specific limits")

    @validator('module')
    def validate_module(cls, v):
        """Validate module name"""
        v = sanitize_input(v, max_length=50)
        
        # Check if module is valid
        valid_modules = [
            'patients', 'appointments', 'clinical', 'financial', 'stock',
            'procedures', 'tiss', 'bi', 'telemed', 'mobile', 'api',
            'reports', 'backup', 'integration'
        ]
        
        if v not in valid_modules:
            raise ValueError(f'Invalid module: {v}. Valid modules: {", ".join(valid_modules)}')
        
        return v

    @validator('limits_json')
    def validate_limits_json(cls, v):
        """Validate limits JSON structure"""
        if v is not None:
            if not isinstance(v, dict):
                raise ValueError('Limits must be a dictionary')
            
            # Validate common limit types
            valid_limit_types = [
                'max_records', 'max_users', 'max_storage_gb', 'max_api_calls_per_day',
                'max_exports_per_day', 'max_backups', 'max_integrations', 'retention_days',
                'concurrent_sessions', 'custom_fields'
            ]
            
            for key in v.keys():
                if key not in valid_limit_types:
                    raise ValueError(f'Invalid limit type: {key}. Valid types: {", ".join(valid_limit_types)}')
                
                # Validate limit values
                value = v[key]
                if isinstance(value, (int, float)):
                    if value < 0:
                        raise ValueError(f'Limit value for {key} cannot be negative')
                elif not isinstance(value, (str, bool, list, dict)):
                    raise ValueError(f'Invalid limit value type for {key}')
        
        return v


class EntitlementCreate(EntitlementBase):
    """Entitlement creation schema"""
    license_id: uuid.UUID = Field(..., description="License ID")


class EntitlementUpdate(BaseModel):
    """Entitlement update schema"""
    enabled: Optional[bool] = None
    limits_json: Optional[Dict[str, Any]] = None

    @validator('limits_json')
    def validate_limits_json(cls, v):
        """Validate limits JSON structure"""
        if v is not None:
            if not isinstance(v, dict):
                raise ValueError('Limits must be a dictionary')
            
            valid_limit_types = [
                'max_records', 'max_users', 'max_storage_gb', 'max_api_calls_per_day',
                'max_exports_per_day', 'max_backups', 'max_integrations', 'retention_days',
                'concurrent_sessions', 'custom_fields'
            ]
            
            for key in v.keys():
                if key not in valid_limit_types:
                    raise ValueError(f'Invalid limit type: {key}')
                
                value = v[key]
                if isinstance(value, (int, float)):
                    if value < 0:
                        raise ValueError(f'Limit value for {key} cannot be negative')
                elif not isinstance(value, (str, bool, list, dict)):
                    raise ValueError(f'Invalid limit value type for {key}')
        
        return v


class EntitlementResponse(EntitlementBase):
    """Entitlement response schema"""
    id: uuid.UUID = Field(..., description="Entitlement ID")
    license_id: uuid.UUID = Field(..., description="License ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    limits: Dict[str, Any] = Field(..., description="Module limits")

    class Config:
        from_attributes = True


class EntitlementListResponse(BaseModel):
    """Entitlement list response schema"""
    id: uuid.UUID
    license_id: uuid.UUID
    module: str
    enabled: bool
    limits: Dict[str, Any]

    class Config:
        from_attributes = True


class EntitlementSummary(BaseModel):
    """Entitlement summary schema"""
    module: str
    enabled: bool
    limits: Dict[str, Any]

    class Config:
        from_attributes = True


class LimitUpdate(BaseModel):
    """Limit update schema"""
    limit_name: str = Field(..., min_length=1, max_length=50, description="Limit name")
    limit_value: Any = Field(..., description="Limit value")

    @validator('limit_name')
    def validate_limit_name(cls, v):
        """Validate limit name"""
        v = sanitize_input(v, max_length=50)
        
        valid_limit_types = [
            'max_records', 'max_users', 'max_storage_gb', 'max_api_calls_per_day',
            'max_exports_per_day', 'max_backups', 'max_integrations', 'retention_days',
            'concurrent_sessions', 'custom_fields'
        ]
        
        if v not in valid_limit_types:
            raise ValueError(f'Invalid limit name: {v}. Valid names: {", ".join(valid_limit_types)}')
        
        return v

    @validator('limit_value')
    def validate_limit_value(cls, v, values):
        """Validate limit value"""
        if 'limit_name' in values:
            limit_name = values['limit_name']
            
            # Validate based on limit type
            if limit_name in ['max_records', 'max_users', 'max_storage_gb', 'max_api_calls_per_day',
                            'max_exports_per_day', 'max_backups', 'max_integrations', 'retention_days',
                            'concurrent_sessions']:
                if not isinstance(v, (int, float)):
                    raise ValueError(f'Limit value for {limit_name} must be a number')
                if v < 0:
                    raise ValueError(f'Limit value for {limit_name} cannot be negative')
            elif limit_name == 'custom_fields':
                if not isinstance(v, (list, dict)):
                    raise ValueError(f'Limit value for {limit_name} must be a list or dictionary')
        
        return v


class ModuleLimits(BaseModel):
    """Module limits schema"""
    module: str = Field(..., description="Module name")
    limits: Dict[str, Any] = Field(..., description="Module limits")

    @validator('module')
    def validate_module(cls, v):
        """Validate module name"""
        v = sanitize_input(v, max_length=50)
        
        valid_modules = [
            'patients', 'appointments', 'clinical', 'financial', 'stock',
            'procedures', 'tiss', 'bi', 'telemed', 'mobile', 'api',
            'reports', 'backup', 'integration'
        ]
        
        if v not in valid_modules:
            raise ValueError(f'Invalid module: {v}')
        
        return v


class EntitlementCheck(BaseModel):
    """Entitlement check schema"""
    module: str = Field(..., description="Module to check")
    current_value: Optional[int] = Field(None, ge=0, description="Current value for limit checking")

    @validator('module')
    def validate_module(cls, v):
        """Validate module name"""
        v = sanitize_input(v, max_length=50)
        
        valid_modules = [
            'patients', 'appointments', 'clinical', 'financial', 'stock',
            'procedures', 'tiss', 'bi', 'telemed', 'mobile', 'api',
            'reports', 'backup', 'integration'
        ]
        
        if v not in valid_modules:
            raise ValueError(f'Invalid module: {v}')
        
        return v


class EntitlementCheckResponse(BaseModel):
    """Entitlement check response schema"""
    module: str = Field(..., description="Module name")
    enabled: bool = Field(..., description="Whether module is enabled")
    has_limit: bool = Field(..., description="Whether module has limits")
    within_limit: Optional[bool] = Field(None, description="Whether current value is within limit")
    remaining_limit: Optional[int] = Field(None, description="Remaining limit")
    limits: Dict[str, Any] = Field(..., description="Module limits")


class BulkEntitlementUpdate(BaseModel):
    """Bulk entitlement update schema"""
    entitlements: List[Dict[str, Any]] = Field(..., description="List of entitlement updates")

    @validator('entitlements')
    def validate_entitlements(cls, v):
        """Validate entitlements list"""
        if not isinstance(v, list):
            raise ValueError('Entitlements must be a list')
        
        if len(v) == 0:
            raise ValueError('Entitlements list cannot be empty')
        
        if len(v) > 100:
            raise ValueError('Cannot update more than 100 entitlements at once')
        
        for i, entitlement in enumerate(v):
            if not isinstance(entitlement, dict):
                raise ValueError(f'Entitlement {i} must be a dictionary')
            
            required_fields = ['module']
            for field in required_fields:
                if field not in entitlement:
                    raise ValueError(f'Entitlement {i} missing required field: {field}')
            
            # Validate module name
            module = entitlement.get('module')
            if not isinstance(module, str) or len(module) == 0:
                raise ValueError(f'Entitlement {i} module must be a non-empty string')
        
        return v


"""
Clinic Pydantic schemas
"""

from datetime import date, datetime, timezone
from typing import List, Optional, Union, Any
from pydantic import BaseModel, Field, validator, field_validator, model_validator
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
    created_at: date = Field(..., description="Creation date")
    updated_at: Optional[date] = Field(None, description="Last update date")
    
    @model_validator(mode='before')
    @classmethod
    def convert_datetime_fields(cls, data: Any) -> Any:
        """Convert datetime objects to date objects before validation - CRITICAL for Pydantic v2"""
        def convert_dt_to_date(dt_value: Any) -> Any:
            """Helper to convert datetime to date - absolutely must return a date object"""
            if dt_value is None:
                return None
            if isinstance(dt_value, date):
                # Already a date, but create new instance to be absolutely sure
                return date(dt_value.year, dt_value.month, dt_value.day)
            if isinstance(dt_value, datetime):
                # For timezone-aware datetimes, convert to UTC first
                if dt_value.tzinfo is not None:
                    dt_value = dt_value.astimezone(timezone.utc)
                # CRITICAL: Create a NEW date object - don't use .date() method
                return date(dt_value.year, dt_value.month, dt_value.day)
            # If it has a date() method, use it but verify result
            if hasattr(dt_value, 'date'):
                dt_result = dt_value.date()
                if isinstance(dt_result, datetime):
                    if dt_result.tzinfo is not None:
                        dt_result = dt_result.astimezone(timezone.utc)
                    return date(dt_result.year, dt_result.month, dt_result.day)
                if isinstance(dt_result, date):
                    return date(dt_result.year, dt_result.month, dt_result.day)
            return dt_value
        
        # Handle dict input (most common case)
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if key in ('created_at', 'updated_at'):
                    result[key] = convert_dt_to_date(value)
                else:
                    result[key] = value
            return result
        
        # Handle object with attributes (from_attributes=True)
        if hasattr(data, '__dict__'):
            obj_dict = {}
            for key, value in data.__dict__.items():
                if key in ('created_at', 'updated_at'):
                    obj_dict[key] = convert_dt_to_date(value)
                else:
                    obj_dict[key] = value
            return obj_dict
        
        # Handle other cases (like SQLAlchemy model directly)
        if hasattr(data, 'created_at') or hasattr(data, 'updated_at'):
            obj_dict = {}
            for attr in dir(data):
                if not attr.startswith('_'):
                    try:
                        value = getattr(data, attr, None)
                        if attr in ('created_at', 'updated_at'):
                            obj_dict[attr] = convert_dt_to_date(value)
                        elif not callable(value):
                            obj_dict[attr] = value
                    except:
                        pass
            return obj_dict
        
        return data
    
    @field_validator('created_at', 'updated_at', mode='before')
    @classmethod
    def convert_datetime_to_date(cls, v: Union[date, datetime, str, None]) -> Optional[date]:
        """Convert datetime objects to date objects (backup validator)"""
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            # Extract date from datetime (handles both naive and timezone-aware)
            if v.tzinfo is not None:
                # For timezone-aware, convert to UTC first
                v = v.astimezone(timezone.utc)
            return date(v.year, v.month, v.day)
        # If it's a string, try to parse it
        if isinstance(v, str):
            try:
                # Try parsing as datetime first
                dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc)
                return date(dt.year, dt.month, dt.day)
            except:
                try:
                    # Try parsing as date
                    return datetime.strptime(v, '%Y-%m-%d').date()
                except:
                    pass
        return v
    
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

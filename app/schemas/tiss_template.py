"""
TISS Template Pydantic schemas
"""

from datetime import datetime
from typing import Optional, List, Union
from pydantic import BaseModel, Field, field_validator
from app.models.tiss_template import TissTemplateCategory


class TissTemplateBase(BaseModel):
    """Base TISS template schema"""
    name: str = Field(..., max_length=200, description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    category: TissTemplateCategory = Field(..., description="Template category")
    xml_template: str = Field(..., description="XML template with variables like {{VARIABLE_NAME}}")
    is_default: bool = Field(default=False, description="Whether this is a default template")
    is_active: bool = Field(default=True, description="Whether the template is active")
    
    @field_validator('category', mode='before')
    @classmethod
    def normalize_category(cls, v):
        """Normalize category to enum value (lowercase)"""
        if isinstance(v, str):
            v = v.lower()
            try:
                return TissTemplateCategory(v)
            except ValueError:
                # If invalid, default to custom
                return TissTemplateCategory.CUSTOM
        return v
    
    class Config:
        use_enum_values = True  # Use enum values instead of enum objects when serializing


class TissTemplateCreate(TissTemplateBase):
    """Schema for creating a TISS template"""
    pass


class TissTemplateUpdate(BaseModel):
    """Schema for updating a TISS template"""
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    category: Optional[TissTemplateCategory] = None
    xml_template: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class TissTemplateResponse(TissTemplateBase):
    """Schema for TISS template response"""
    id: int
    variables: List[str] = Field(default_factory=list, description="List of variables found in template")
    clinic_id: int
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


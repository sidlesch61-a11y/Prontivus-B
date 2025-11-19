"""
Authentication Schemas
Pydantic models for authentication requests and responses
"""

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime
from app.models import UserRole
from app.core.validators import validate_password_strength, validate_email, sanitize_input


# ==================== Request Schemas ====================

class LoginRequest(BaseModel):
    """Login request schema"""
    username_or_email: str = Field(
        ...,
        description="Username or email address",
        min_length=3,
        max_length=100
    )
    password: str = Field(
        ...,
        description="User password",
        min_length=6,
        max_length=100
    )
    expected_role: Optional[str] = Field(
        None,
        description="Expected user role for role-based login verification (patient or staff)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "username_or_email": "admin@clinic.com",
                "password": "secretpassword",
                "expected_role": "staff"
            }
        }


class RegisterRequest(BaseModel):
    """User registration request schema"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    clinic_id: int = Field(..., description="Clinic ID the user belongs to")
    role: UserRole = Field(default=UserRole.PATIENT, description="User role")

    @validator('password')
    def validate_password(cls, v):
        return validate_password_strength(v)

    @validator('email')
    def validate_email_field(cls, v):
        return validate_email(str(v))

    @validator('username', 'first_name', 'last_name')
    def sanitize_text_fields(cls, v):
        if v:
            return sanitize_input(v, max_length=100)
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "johndoe",
                "email": "john.doe@example.com",
                "password": "securepassword",
                "first_name": "John",
                "last_name": "Doe",
                "clinic_id": 1,
                "role": "patient"
            }
        }


class ChangePasswordRequest(BaseModel):
    """Change password request schema"""
    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=6, description="New password")


class ForgotPasswordRequest(BaseModel):
    """Forgot password request schema"""
    email: EmailStr = Field(..., description="User email address")
    
    @validator('email')
    def validate_email_field(cls, v):
        return validate_email(str(v))


class ResetPasswordRequest(BaseModel):
    """Reset password request schema"""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password")
    
    @validator('new_password')
    def validate_password(cls, v):
        return validate_password_strength(v)


# ==================== Response Schemas ====================

class TokenResponse(BaseModel):
    """JWT token response schema"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: Optional[str] = Field(None, description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 1800
            }
        }


class ClinicInfo(BaseModel):
    """Clinic information for user response"""
    id: int
    name: str
    legal_name: str
    tax_id: str
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    is_active: bool
    license_key: Optional[str]
    expiration_date: Optional[datetime]
    max_users: int
    active_modules: List[str]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    """User data response schema"""
    id: int
    username: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: UserRole
    role_id: Optional[int] = None  # Role ID from menu system
    role_name: Optional[str] = None  # Role name (e.g., "SuperAdmin", "Medico")
    is_active: bool
    is_verified: bool
    clinic_id: int
    clinic: Optional[ClinicInfo] = None
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "username": "johndoe",
                "email": "john.doe@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "role": "doctor",
                "is_active": True,
                "is_verified": True,
                "clinic_id": 1,
                "clinic": {
                    "id": 1,
                    "name": "Clinic Name",
                    "legal_name": "Legal Clinic Name",
                    "tax_id": "12345678000199",
                    "is_active": True,
                    "max_users": 10,
                    "active_modules": ["appointments", "clinical", "financial"]
                }
            }
        }


# Menu schemas are imported from menu.py to avoid duplication


class LoginResponse(BaseModel):
    """Complete login response with token, user data, and menu structure"""
    access_token: str
    refresh_token: Optional[str]
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
    menu: Optional[List[dict]] = None  # Menu structure for the user (using dict to avoid circular import)
    permissions: Optional[List[str]] = None  # User permissions list
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 1800,
                "user": {
                    "id": 1,
                    "username": "johndoe",
                    "email": "john.doe@example.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "role": "doctor",
                    "is_active": True,
                    "is_verified": True,
                    "clinic_id": 1
                },
                "menu": [],
                "permissions": []
            }
        }


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Operation completed successfully"
            }
        }


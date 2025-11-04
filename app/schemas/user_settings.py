"""
User Settings Schemas
Pydantic schemas for user settings validation and serialization
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class NotificationSettings(BaseModel):
    """Notification preferences"""
    email: bool = True
    push: bool = True
    sms: bool = False
    appointmentReminders: bool = True
    systemUpdates: bool = True
    marketing: bool = False


class PrivacySettings(BaseModel):
    """Privacy preferences"""
    profileVisibility: str = Field(default="contacts", pattern="^(public|contacts|private)$")
    showOnlineStatus: bool = True
    allowDirectMessages: bool = True
    dataSharing: bool = False


class AppearanceSettings(BaseModel):
    """Appearance preferences"""
    theme: str = Field(default="system", pattern="^(light|dark|system)$")
    language: str = Field(default="pt-BR")
    timezone: str = Field(default="America/Sao_Paulo")
    dateFormat: str = Field(default="DD/MM/YYYY")


class SecuritySettings(BaseModel):
    """Security preferences"""
    twoFactorAuth: bool = False
    loginAlerts: bool = True
    sessionTimeout: int = Field(default=30, ge=5, le=480)
    passwordExpiry: int = Field(default=90, ge=30, le=365)


class UserSettingsUpdate(BaseModel):
    """Schema for updating user settings"""
    phone: Optional[str] = None
    notifications: Optional[Dict[str, Any]] = None
    privacy: Optional[Dict[str, Any]] = None
    appearance: Optional[Dict[str, Any]] = None
    security: Optional[Dict[str, Any]] = None


class UserSettingsResponse(BaseModel):
    """Schema for user settings response"""
    id: int
    user_id: int
    phone: Optional[str]
    notifications: Dict[str, Any]
    privacy: Dict[str, Any]
    appearance: Dict[str, Any]
    security: Dict[str, Any]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class UserSettingsFullResponse(BaseModel):
    """Full user settings response including profile info"""
    profile: Dict[str, Any]
    notifications: Dict[str, Any]
    privacy: Dict[str, Any]
    appearance: Dict[str, Any]
    security: Dict[str, Any]


"""
License model for the licensing module
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class LicenseStatus(str, Enum):
    """License status enumeration"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class LicensePlan(str, Enum):
    """License plan enumeration"""
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class License(Base):
    """License model for managing software licenses"""
    
    __tablename__ = "licenses"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Tenant relationship (Clinic uses integer PK)
    tenant_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True)
    
    # License details
    # Store plan as string to meet requirement; API may still use enum values
    plan = Column(String(50), nullable=False)
    modules = Column(JSON, nullable=False, default=list)  # List of enabled modules
    users_limit = Column(Integer, nullable=False, default=1)
    units_limit = Column(Integer, nullable=True)  # For multi-clinic licenses
    
    # License period
    start_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    end_at = Column(DateTime(timezone=True), nullable=False)
    
    # License status
    status = Column(SQLEnum(LicenseStatus), nullable=False, default=LicenseStatus.ACTIVE)
    
    # Security
    activation_key = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4, unique=True, index=True)
    signature = Column(Text, nullable=True)  # RSA/ECDSA signature for license validation
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    
    # Relationships (decoupled from Clinic.license to avoid conflicting backrefs)
    tenant = relationship(
        "Clinic",
        foreign_keys=[tenant_id],
        primaryjoin="License.tenant_id==Clinic.id"
    )
    activations = relationship("Activation", back_populates="license", cascade="all, delete-orphan")
    entitlements = relationship("Entitlement", back_populates="license", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<License(id={self.id}, plan={self.plan}, status={self.status})>"
    
    @property
    def is_active(self) -> bool:
        """Check if license is currently active"""
        now = datetime.utcnow()
        return (
            self.status == LicenseStatus.ACTIVE and
            self.start_at <= now <= self.end_at
        )
    
    @property
    def is_expired(self) -> bool:
        """Check if license has expired"""
        return datetime.utcnow() > self.end_at
    
    @property
    def days_until_expiry(self) -> int:
        """Get days until license expires"""
        if self.is_expired:
            return 0
        delta = self.end_at - datetime.utcnow()
        return max(0, delta.days)
    
    def get_module_entitlement(self, module: str) -> Optional['Entitlement']:
        """Get entitlement for a specific module"""
        for entitlement in self.entitlements:
            if entitlement.module == module:
                return entitlement
        return None
    
    def is_module_enabled(self, module: str) -> bool:
        """Check if a module is enabled for this license"""
        return module in self.modules
    
    def can_add_user(self, current_user_count: int) -> bool:
        """Check if license can accommodate additional users"""
        return current_user_count < self.users_limit
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert license to dictionary"""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "plan": self.plan,
            "modules": self.modules,
            "users_limit": self.users_limit,
            "units_limit": self.units_limit,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "status": self.status.value,
            "activation_key": str(self.activation_key),
            "is_active": self.is_active,
            "is_expired": self.is_expired,
            "days_until_expiry": self.days_until_expiry,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


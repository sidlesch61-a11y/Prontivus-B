"""
Activation model for tracking license activations
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class ActivationStatus(str, Enum):
    """Activation status enumeration"""
    ACTIVE = "active"
    MIGRATED = "migrated"
    REVOKED = "revoked"


class Activation(Base):
    """Activation model for tracking license activations on different instances"""
    
    __tablename__ = "activations"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # License relationship
    license_id = Column(UUID(as_uuid=True), ForeignKey("licenses.id"), nullable=False, index=True)
    
    # Instance identification
    instance_id = Column(String(255), nullable=False, unique=True, index=True)
    
    # Device information
    device_info = Column(JSON, nullable=True)  # Store device fingerprint, OS, etc.
    
    # Activation timestamps
    activated_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    last_check_at = Column(DateTime(timezone=True), nullable=True)
    
    # Activation status
    status = Column(SQLEnum(ActivationStatus), nullable=False, default=ActivationStatus.ACTIVE)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    
    # Relationships
    license = relationship("License", back_populates="activations")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('license_id', 'instance_id', name='uq_license_instance'),
    )
    
    def __repr__(self):
        return f"<Activation(id={self.id}, instance_id={self.instance_id}, status={self.status})>"
    
    @property
    def is_active(self) -> bool:
        """Check if activation is currently active"""
        return self.status == ActivationStatus.ACTIVE
    
    @property
    def days_since_activation(self) -> int:
        """Get days since activation"""
        if not self.activated_at:
            return 0
        delta = datetime.utcnow() - self.activated_at
        return delta.days
    
    @property
    def days_since_last_check(self) -> Optional[int]:
        """Get days since last check"""
        if not self.last_check_at:
            return None
        delta = datetime.utcnow() - self.last_check_at
        return delta.days
    
    def update_last_check(self):
        """Update the last check timestamp"""
        self.last_check_at = datetime.utcnow()
    
    def revoke(self):
        """Revoke this activation"""
        self.status = ActivationStatus.REVOKED
        self.updated_at = datetime.utcnow()
    
    def migrate(self):
        """Mark activation as migrated"""
        self.status = ActivationStatus.MIGRATED
        self.updated_at = datetime.utcnow()
    
    def get_device_fingerprint(self) -> Optional[str]:
        """Get device fingerprint from device_info"""
        if not self.device_info:
            return None
        return self.device_info.get('fingerprint')
    
    def get_os_info(self) -> Optional[Dict[str, Any]]:
        """Get OS information from device_info"""
        if not self.device_info:
            return None
        return self.device_info.get('os_info')
    
    def get_browser_info(self) -> Optional[Dict[str, Any]]:
        """Get browser information from device_info"""
        if not self.device_info:
            return None
        return self.device_info.get('browser_info')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert activation to dictionary"""
        return {
            "id": str(self.id),
            "license_id": str(self.license_id),
            "instance_id": self.instance_id,
            "device_info": self.device_info,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "last_check_at": self.last_check_at.isoformat() if self.last_check_at else None,
            "status": self.status.value,
            "is_active": self.is_active,
            "days_since_activation": self.days_since_activation,
            "days_since_last_check": self.days_since_last_check,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


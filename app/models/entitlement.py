"""
Entitlement model for managing module-specific permissions and limits
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Boolean, ForeignKey, JSON, UniqueConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Entitlement(Base):
    """Entitlement model for managing module-specific permissions and limits"""
    
    __tablename__ = "entitlements"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # License relationship
    license_id = Column(UUID(as_uuid=True), ForeignKey("licenses.id"), nullable=False, index=True)
    
    # Module information
    module = Column(String(50), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    
    # Module-specific limits and configuration
    limits_json = Column(JSON, nullable=True)  # Store module-specific limits and settings
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    
    # Relationships
    license = relationship("License", back_populates="entitlements")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('license_id', 'module', name='uq_license_module'),
    )
    
    def __repr__(self):
        return f"<Entitlement(id={self.id}, module={self.module}, enabled={self.enabled})>"
    
    @property
    def is_enabled(self) -> bool:
        """Check if entitlement is enabled"""
        return self.enabled
    
    def get_limit(self, limit_name: str, default: Any = None) -> Any:
        """Get a specific limit value"""
        if not self.limits_json:
            return default
        return self.limits_json.get(limit_name, default)
    
    def set_limit(self, limit_name: str, value: Any):
        """Set a specific limit value"""
        if not self.limits_json:
            self.limits_json = {}
        self.limits_json[limit_name] = value
    
    def get_all_limits(self) -> Dict[str, Any]:
        """Get all limits as a dictionary"""
        return self.limits_json or {}
    
    def update_limits(self, limits: Dict[str, Any]):
        """Update multiple limits at once"""
        if not self.limits_json:
            self.limits_json = {}
        self.limits_json.update(limits)
    
    def has_limit(self, limit_name: str) -> bool:
        """Check if a specific limit is defined"""
        if not self.limits_json:
            return False
        return limit_name in self.limits_json
    
    def get_module_config(self) -> Dict[str, Any]:
        """Get module configuration including limits"""
        config = {
            "module": self.module,
            "enabled": self.enabled,
            "limits": self.get_all_limits()
        }
        return config
    
    def is_within_limit(self, limit_name: str, current_value: int) -> bool:
        """Check if current value is within the specified limit"""
        limit_value = self.get_limit(limit_name)
        if limit_value is None:
            return True  # No limit set
        return current_value <= limit_value
    
    def get_remaining_limit(self, limit_name: str, current_value: int) -> Optional[int]:
        """Get remaining limit for a specific limit type"""
        limit_value = self.get_limit(limit_name)
        if limit_value is None:
            return None  # No limit set
        return max(0, limit_value - current_value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entitlement to dictionary"""
        return {
            "id": str(self.id),
            "license_id": str(self.license_id),
            "module": self.module,
            "enabled": self.enabled,
            "limits": self.get_all_limits(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Common module names for reference
class ModuleName:
    """Common module names used in the system"""
    PATIENTS = "patients"
    APPOINTMENTS = "appointments"
    CLINICAL = "clinical"
    FINANCIAL = "financial"
    STOCK = "stock"
    PROCEDURES = "procedures"
    TISS = "tiss"
    BI = "bi"
    TELEMED = "telemed"
    MOBILE = "mobile"
    API = "api"
    REPORTS = "reports"
    BACKUP = "backup"
    INTEGRATION = "integration"


# Common limit types for reference
class LimitType:
    """Common limit types used across modules"""
    MAX_RECORDS = "max_records"
    MAX_USERS = "max_users"
    MAX_STORAGE_GB = "max_storage_gb"
    MAX_API_CALLS_PER_DAY = "max_api_calls_per_day"
    MAX_EXPORTS_PER_DAY = "max_exports_per_day"
    MAX_BACKUPS = "max_backups"
    MAX_INTEGRATIONS = "max_integrations"
    RETENTION_DAYS = "retention_days"
    CONCURRENT_SESSIONS = "concurrent_sessions"
    CUSTOM_FIELDS = "custom_fields"


"""
AI Configuration Model
Stores AI integration settings per clinic with token usage tracking
"""

from sqlalchemy import Column, Integer, ForeignKey, DateTime, JSON, Boolean, String, Text, Float, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class AIConfig(Base):
    """
    AI Configuration Model
    Stores AI integration configuration per clinic
    """
    __tablename__ = "ai_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True, unique=True)
    
    # Basic Configuration
    enabled = Column(Boolean, default=False, nullable=False)
    provider = Column(String(50), nullable=True)  # "openai", "google", "anthropic", "azure"
    api_key_encrypted = Column(Text, nullable=True)  # Encrypted API key
    model = Column(String(100), nullable=True)
    base_url = Column(String(255), nullable=True)
    max_tokens = Column(Integer, default=2000, nullable=False)
    temperature = Column(Float, default=0.7, nullable=False)
    
    # Features Configuration
    features = Column(JSON, nullable=False, default=dict)
    # Structure:
    # {
    #   "clinical_analysis": {"enabled": false, "description": "..."},
    #   "diagnosis_suggestions": {"enabled": false, "description": "..."},
    #   "predictive_analysis": {"enabled": false, "description": "..."},
    #   "virtual_assistant": {"enabled": false, "description": "..."}
    # }
    
    # Usage Statistics and Token Tracking
    usage_stats = Column(JSON, nullable=False, default=dict)
    # Structure:
    # {
    #   "total_tokens": 0,
    #   "tokens_this_month": 0,
    #   "tokens_this_year": 0,
    #   "requests_count": 0,
    #   "successful_requests": 0,
    #   "failed_requests": 0,
    #   "last_reset_date": null,
    #   "last_request_date": null,
    #   "average_response_time_ms": 0,
    #   "documents_processed": 0,
    #   "suggestions_generated": 0,
    #   "approval_rate": 0.0
    # }
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    clinic = relationship("Clinic")
    
    __table_args__ = (
        UniqueConstraint('clinic_id', name='uq_ai_config_clinic'),
    )
    
    def __repr__(self):
        return f"<AIConfig(clinic_id={self.clinic_id}, provider={self.provider}, enabled={self.enabled})>"
    
    def get_monthly_token_usage(self) -> int:
        """Get tokens used this month"""
        return self.usage_stats.get("tokens_this_month", 0)
    
    def get_total_token_usage(self) -> int:
        """Get total tokens used"""
        return self.usage_stats.get("total_tokens", 0)
    
    def can_use_tokens(self, required_tokens: int, monthly_limit: int) -> bool:
        """Check if clinic can use the required tokens"""
        if monthly_limit <= 0:  # Unlimited
            return True
        return self.get_monthly_token_usage() + required_tokens <= monthly_limit
    
    def to_dict(self, include_api_key: bool = False):
        """Convert to dictionary, optionally including API key"""
        result = {
            "id": self.id,
            "clinic_id": self.clinic_id,
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "features": self.features,
            "usage_stats": self.usage_stats,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_api_key:
            result["api_key"] = self.api_key_encrypted  # Will be decrypted by service
        return result


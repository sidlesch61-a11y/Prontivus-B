"""
Password Reset Token Model
Stores password reset tokens for users
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from database import Base
from app.models import BaseModel


class PasswordResetToken(BaseModel):
    """
    Password Reset Token Model
    Stores temporary tokens for password reset functionality
    """
    __tablename__ = "password_reset_tokens"
    
    # Token Information
    token = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used = Column(Boolean, default=False, nullable=False, index=True)
    
    # Relationships
    # user = relationship("User", back_populates="password_reset_tokens")
    
    def __repr__(self):
        return f"<PasswordResetToken(id={self.id}, user_id={self.user_id}, used={self.used})>"
    
    @property
    def is_expired(self):
        """Check if token is expired"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) > self.expires_at


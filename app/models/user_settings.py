"""
User Settings Model
Stores user preferences and settings for notifications, privacy, appearance, and security
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, JSON, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class UserSettings(Base):
    """
    User Settings Model
    Stores user preferences for notifications, privacy, appearance, and security
    """
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    
    # Profile Information (can be overridden from User model)
    phone = Column(String(20), nullable=True)
    
    # Notification Preferences (stored as JSON for flexibility)
    notifications = Column(JSON, nullable=False, default=dict)
    # Example structure:
    # {
    #   "email": true,
    #   "push": true,
    #   "sms": false,
    #   "appointmentReminders": true,
    #   "systemUpdates": true,
    #   "marketing": false
    # }
    
    # Privacy Settings (stored as JSON)
    privacy = Column(JSON, nullable=False, default=dict)
    # Example structure:
    # {
    #   "profileVisibility": "contacts",
    #   "showOnlineStatus": true,
    #   "allowDirectMessages": true,
    #   "dataSharing": false
    # }
    
    # Appearance Settings (stored as JSON)
    appearance = Column(JSON, nullable=False, default=dict)
    # Example structure:
    # {
    #   "theme": "system",
    #   "language": "pt-BR",
    #   "timezone": "America/Sao_Paulo",
    #   "dateFormat": "DD/MM/YYYY"
    # }
    
    # Security Settings (stored as JSON)
    security = Column(JSON, nullable=False, default=dict)
    # Example structure:
    # {
    #   "twoFactorAuth": false,
    #   "loginAlerts": true,
    #   "sessionTimeout": 30,
    #   "passwordExpiry": 90
    # }
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="settings")
    
    def __repr__(self):
        return f"<UserSettings(id={self.id}, user_id={self.user_id})>"


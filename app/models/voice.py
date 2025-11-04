"""
Voice processing models for clinical documentation
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, LargeBinary, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from database import Base

class VoiceSession(Base):
    """Model for storing encrypted voice session data"""
    __tablename__ = "voice_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    
    # Encrypted audio data (HIPAA compliant)
    encrypted_audio_data = Column(LargeBinary, nullable=False)
    
    # Session metadata
    language = Column(String(10), default="pt-BR")
    duration_seconds = Column(Integer, nullable=True)
    confidence_score = Column(String(10), nullable=True)  # Store as string to avoid precision issues
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # Auto-delete for compliance
    processed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="voice_sessions")
    appointment = relationship("Appointment", back_populates="voice_sessions")
    
    def __repr__(self):
        return f"<VoiceSession(session_id='{self.session_id}', user_id={self.user_id})>"

class VoiceCommand(Base):
    """Model for storing voice commands and their processing results"""
    __tablename__ = "voice_commands"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), ForeignKey("voice_sessions.session_id"), nullable=False)
    command_type = Column(String(50), nullable=False)  # subjective, objective, assessment, plan, etc.
    raw_text = Column(Text, nullable=False)
    processed_content = Column(Text, nullable=False)
    confidence_score = Column(String(10), nullable=True)
    
    # Medical analysis results
    medical_terms = Column(Text, nullable=True)  # JSON string
    icd10_codes = Column(Text, nullable=True)  # JSON string
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    voice_session = relationship("VoiceSession")
    
    def __repr__(self):
        return f"<VoiceCommand(session_id='{self.session_id}', type='{self.command_type}')>"

class MedicalTerm(Base):
    """Model for storing medical terminology and ICD-10 mappings"""
    __tablename__ = "medical_terms"
    
    id = Column(Integer, primary_key=True, index=True)
    term = Column(String(255), nullable=False, index=True)
    category = Column(String(50), nullable=False)  # symptom, diagnosis, medication, etc.
    icd10_codes = Column(Text, nullable=True)  # JSON array of ICD-10 codes
    synonyms = Column(Text, nullable=True)  # JSON array of synonyms
    confidence = Column(String(10), nullable=True)
    
    # Language and region
    language = Column(String(10), default="pt-BR")
    region = Column(String(10), default="BR")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<MedicalTerm(term='{self.term}', category='{self.category}')>"

class VoiceConfiguration(Base):
    """Model for storing voice processing configuration per user/clinic"""
    __tablename__ = "voice_configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=True)
    
    # Voice processing settings
    provider = Column(String(20), default="google")  # google, aws, azure
    language = Column(String(10), default="pt-BR")
    model = Column(String(50), default="medical_dictation")
    enable_auto_punctuation = Column(String(10), default="true")
    enable_word_time_offsets = Column(String(10), default="true")
    confidence_threshold = Column(String(10), default="0.8")
    
    # Medical terminology settings
    custom_terms = Column(Text, nullable=True)  # JSON array of custom terms
    enable_icd10_suggestions = Column(String(10), default="true")
    enable_medication_recognition = Column(String(10), default="true")
    
    # Privacy and compliance settings
    auto_delete_after_hours = Column(Integer, default=24)
    enable_encryption = Column(String(10), default="true")
    enable_audit_logging = Column(String(10), default="true")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    clinic = relationship("Clinic")
    
    def __repr__(self):
        return f"<VoiceConfiguration(user_id={self.user_id}, clinic_id={self.clinic_id})>"

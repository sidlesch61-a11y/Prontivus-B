"""
Voice processing schemas for clinical documentation
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class VoiceSessionCreate(BaseModel):
    """Schema for creating a voice session"""
    appointment_id: int
    language: str = "pt-BR"

class VoiceSessionResponse(BaseModel):
    """Schema for voice session response"""
    session_id: str
    appointment_id: int
    created_at: datetime
    expires_at: datetime

class VoiceCommandResponse(BaseModel):
    """Schema for voice command response"""
    id: int
    session_id: str
    command_type: str
    raw_text: str
    processed_content: str
    confidence_score: Optional[float]
    medical_terms: Optional[List[str]]
    icd10_codes: Optional[List[str]]
    created_at: datetime

class MedicalTermResponse(BaseModel):
    """Schema for medical term response"""
    id: int
    term: str
    category: str
    icd10_codes: List[str]
    synonyms: List[str]
    confidence: Optional[float]
    language: str

class VoiceConfigurationResponse(BaseModel):
    """Schema for voice configuration response"""
    provider: str = "google"
    language: str = "pt-BR"
    model: str = "medical_dictation"
    enable_auto_punctuation: bool = True
    enable_word_time_offsets: bool = True
    confidence_threshold: float = 0.8
    enable_icd10_suggestions: bool = True
    enable_medication_recognition: bool = True
    auto_delete_after_hours: int = 24
    enable_encryption: bool = True
    enable_audit_logging: bool = True

class VoiceCommandCreate(BaseModel):
    """Schema for creating a voice command"""
    session_id: str
    command_type: str
    raw_text: str
    processed_content: str
    confidence_score: Optional[float] = None
    medical_terms: Optional[List[str]] = None
    icd10_codes: Optional[List[str]] = None

class VoiceCommandUpdate(BaseModel):
    """Schema for updating a voice command"""
    processed_content: Optional[str] = None
    confidence_score: Optional[float] = None
    medical_terms: Optional[List[str]] = None
    icd10_codes: Optional[List[str]] = None

class MedicalTermCreate(BaseModel):
    """Schema for creating a medical term"""
    term: str
    category: str
    icd10_codes: Optional[List[str]] = None
    synonyms: Optional[List[str]] = None
    confidence: Optional[float] = None
    language: str = "pt-BR"
    region: str = "BR"

class MedicalTermUpdate(BaseModel):
    """Schema for updating a medical term"""
    term: Optional[str] = None
    category: Optional[str] = None
    icd10_codes: Optional[List[str]] = None
    synonyms: Optional[List[str]] = None
    confidence: Optional[float] = None

class VoiceConfigurationCreate(BaseModel):
    """Schema for creating voice configuration"""
    user_id: Optional[int] = None
    clinic_id: Optional[int] = None
    provider: str = "google"
    language: str = "pt-BR"
    model: str = "medical_dictation"
    enable_auto_punctuation: bool = True
    enable_word_time_offsets: bool = True
    confidence_threshold: float = 0.8
    custom_terms: Optional[List[str]] = None
    enable_icd10_suggestions: bool = True
    enable_medication_recognition: bool = True
    auto_delete_after_hours: int = 24
    enable_encryption: bool = True
    enable_audit_logging: bool = True

class VoiceConfigurationUpdate(BaseModel):
    """Schema for updating voice configuration"""
    provider: Optional[str] = None
    language: Optional[str] = None
    model: Optional[str] = None
    enable_auto_punctuation: Optional[bool] = None
    enable_word_time_offsets: Optional[bool] = None
    confidence_threshold: Optional[float] = None
    custom_terms: Optional[List[str]] = None
    enable_icd10_suggestions: Optional[bool] = None
    enable_medication_recognition: Optional[bool] = None
    auto_delete_after_hours: Optional[int] = None
    enable_encryption: Optional[bool] = None
    enable_audit_logging: Optional[bool] = None

class VoiceProcessingResult(BaseModel):
    """Schema for voice processing result"""
    transcription: str
    commands: List[Dict[str, Any]]
    medical_terms: List[Dict[str, Any]]
    structured_data: Dict[str, Any]
    confidence: float
    session_id: str
    timestamp: str

class SOAPNoteData(BaseModel):
    """Schema for SOAP note structured data"""
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""

class VoiceStructuredData(BaseModel):
    """Schema for structured voice data"""
    soap_notes: SOAPNoteData
    symptoms: List[Dict[str, Any]] = []
    diagnoses: List[Dict[str, Any]] = []
    medications: List[Dict[str, Any]] = []
    vital_signs: Dict[str, Any] = {}
    icd10_codes: List[str] = []
    confidence_scores: Dict[str, float] = {}

class VoiceCommandSuggestion(BaseModel):
    """Schema for voice command suggestions"""
    command_type: str
    suggestion: str
    description: str
    example: str

class VoiceCommandSuggestions(BaseModel):
    """Schema for voice command suggestions response"""
    suggestions: List[VoiceCommandSuggestion]
    context: str
    appointment_id: int

class VoiceProcessingError(BaseModel):
    """Schema for voice processing error"""
    error_type: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime

class VoiceSessionStatus(BaseModel):
    """Schema for voice session status"""
    session_id: str
    status: str  # active, processing, completed, error
    progress: Optional[float] = None
    message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class VoiceAnalytics(BaseModel):
    """Schema for voice processing analytics"""
    total_sessions: int
    total_processing_time: float
    average_confidence: float
    most_common_commands: List[Dict[str, Any]]
    medical_terms_found: int
    icd10_codes_suggested: int
    error_rate: float
    period: str  # daily, weekly, monthly

class VoiceQualityMetrics(BaseModel):
    """Schema for voice quality metrics"""
    audio_quality: float
    transcription_accuracy: float
    medical_term_recognition: float
    command_extraction: float
    overall_score: float
    recommendations: List[str] = []

class VoicePrivacySettings(BaseModel):
    """Schema for voice privacy settings"""
    enable_encryption: bool = True
    auto_delete_after_hours: int = 24
    enable_audit_logging: bool = True
    data_retention_days: int = 30
    allow_cloud_processing: bool = False
    enable_local_processing: bool = True
    anonymize_audio: bool = True

class VoiceComplianceReport(BaseModel):
    """Schema for voice compliance report"""
    hipaa_compliant: bool
    gdpr_compliant: bool
    data_encrypted: bool
    audit_logs_enabled: bool
    data_retention_compliant: bool
    access_controls_enabled: bool
    last_audit: datetime
    compliance_score: float
    recommendations: List[str] = []

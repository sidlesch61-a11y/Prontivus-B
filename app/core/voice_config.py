"""
Voice Processing Configuration
Settings for voice-to-text clinical documentation
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings

class VoiceSettings(BaseSettings):
    """Voice processing configuration settings"""
    
    # Encryption
    VOICE_ENCRYPTION_KEY: Optional[str] = None
    
    # Google Speech-to-Text
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_PROJECT_ID: Optional[str] = None
    
    # AWS Transcribe
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    
    # Azure Speech Services
    AZURE_SPEECH_KEY: Optional[str] = None
    AZURE_SPEECH_REGION: Optional[str] = None
    
    # Voice processing defaults
    DEFAULT_LANGUAGE: str = "pt-BR"
    DEFAULT_MODEL: str = "medical_dictation"
    DEFAULT_CONFIDENCE_THRESHOLD: float = 0.8
    DEFAULT_AUTO_DELETE_HOURS: int = 24
    
    # Audio processing
    MAX_AUDIO_DURATION_SECONDS: int = 300  # 5 minutes
    MAX_AUDIO_FILE_SIZE_MB: int = 50
    SUPPORTED_AUDIO_FORMATS: list = ["webm", "wav", "mp3", "ogg"]
    
    # Medical terminology
    MEDICAL_TERMS_CACHE_TTL: int = 3600  # 1 hour
    ENABLE_ICD10_SUGGESTIONS: bool = True
    ENABLE_MEDICATION_RECOGNITION: bool = True
    
    # Privacy and compliance
    ENABLE_ENCRYPTION: bool = True
    ENABLE_AUDIT_LOGGING: bool = True
    DATA_RETENTION_DAYS: int = 30
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"  # Ignore extra environment variables
    }

# Global voice settings instance
voice_settings = VoiceSettings()

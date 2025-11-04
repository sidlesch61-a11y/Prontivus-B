"""
Voice Processing Service for Clinical Documentation
Handles speech-to-text conversion with medical terminology support
"""

import asyncio
import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

import aiohttp
import httpx
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.voice_config import voice_settings
from app.models import User, Patient, Appointment, ClinicalRecord, VoiceSession

logger = logging.getLogger(__name__)

class VoiceProvider(Enum):
    GOOGLE = "google"
    AWS = "aws"
    AZURE = "azure"

class VoiceCommandType(Enum):
    SUBJECTIVE = "subjective"
    OBJECTIVE = "objective"
    ASSESSMENT = "assessment"
    PLAN = "plan"
    MEDICATION = "medication"
    DIAGNOSIS = "diagnosis"
    SYMPTOM = "symptom"
    VITAL_SIGNS = "vital_signs"

@dataclass
class VoiceCommand:
    command_type: VoiceCommandType
    content: str
    confidence: float
    timestamp: datetime
    raw_text: str

@dataclass
class MedicalTerm:
    term: str
    category: str
    icd10_codes: List[str]
    synonyms: List[str]
    confidence: float

class VoiceProcessingService:
    """Main service for voice processing and clinical documentation"""
    
    def __init__(self):
        self.encryption_key = self._get_encryption_key()
        self.medical_terms = self._load_medical_terms()
        self.voice_provider = VoiceProvider.GOOGLE  # Default provider
        
    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key for voice data"""
        key_str = voice_settings.VOICE_ENCRYPTION_KEY or Fernet.generate_key().decode()
        return key_str.encode() if isinstance(key_str, str) else key_str
    
    def _load_medical_terms(self) -> Dict[str, MedicalTerm]:
        """Load medical terminology database"""
        return {
            "dor abdominal": MedicalTerm(
                term="dor abdominal",
                category="symptom",
                icd10_codes=["R10.9", "K59.0"],
                synonyms=["dor no abdome", "abdominalgia", "dor de barriga"],
                confidence=0.95
            ),
            "apendicite": MedicalTerm(
                term="apendicite",
                category="diagnosis",
                icd10_codes=["K35.9"],
                synonyms=["apendicite aguda", "inflamação do apêndice"],
                confidence=0.98
            ),
            "febre": MedicalTerm(
                term="febre",
                category="symptom",
                icd10_codes=["R50.9"],
                synonyms=["hipertermia", "temperatura elevada"],
                confidence=0.92
            ),
            "náusea": MedicalTerm(
                term="náusea",
                category="symptom",
                icd10_codes=["R11.0"],
                synonyms=["enjoo", "vontade de vomitar"],
                confidence=0.90
            ),
            "vômito": MedicalTerm(
                term="vômito",
                category="symptom",
                icd10_codes=["R11.0"],
                synonyms=["emese", "vomitar"],
                confidence=0.88
            ),
            "cefaleia": MedicalTerm(
                term="cefaleia",
                category="symptom",
                icd10_codes=["R51"],
                synonyms=["dor de cabeça", "cefalalgia"],
                confidence=0.94
            ),
            "hipertensão": MedicalTerm(
                term="hipertensão",
                category="diagnosis",
                icd10_codes=["I10"],
                synonyms=["pressão alta", "HAS"],
                confidence=0.96
            ),
            "diabetes": MedicalTerm(
                term="diabetes",
                category="diagnosis",
                icd10_codes=["E11.9"],
                synonyms=["DM", "diabetes mellitus"],
                confidence=0.97
            )
        }
    
    async def process_audio_stream(
        self, 
        audio_data: bytes, 
        user_id: int, 
        appointment_id: int,
        session_id: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Process audio stream and return transcription with medical analysis
        
        Args:
            audio_data: Raw audio bytes
            user_id: ID of the user (doctor)
            appointment_id: ID of the appointment
            session_id: Unique session identifier
            db: Database session
            
        Returns:
            Dict containing transcription, commands, and medical terms
        """
        try:
            # Encrypt audio data for HIPAA compliance
            encrypted_audio = self._encrypt_audio_data(audio_data)
            
            # Store encrypted audio temporarily
            await self._store_audio_session(session_id, encrypted_audio, user_id, appointment_id, db)
            
            # Convert speech to text
            transcription = await self._speech_to_text(audio_data)
            
            # Process medical terminology
            medical_analysis = self._analyze_medical_terms(transcription)
            
            # Extract voice commands
            commands = self._extract_voice_commands(transcription)
            
            # Generate structured data
            structured_data = self._generate_structured_data(transcription, medical_analysis, commands)
            
            return {
                "transcription": transcription,
                "commands": [cmd.__dict__ for cmd in commands],
                "medical_terms": [term.__dict__ for term in medical_analysis],
                "structured_data": structured_data,
                "confidence": self._calculate_overall_confidence(transcription, commands),
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing audio stream: {str(e)}")
            raise
    
    async def _speech_to_text(self, audio_data: bytes) -> str:
        """Convert audio to text using configured provider"""
        if self.voice_provider == VoiceProvider.GOOGLE:
            return await self._google_speech_to_text(audio_data)
        elif self.voice_provider == VoiceProvider.AWS:
            return await self._aws_transcribe(audio_data)
        else:
            raise ValueError(f"Unsupported voice provider: {self.voice_provider}")
    
    async def _google_speech_to_text(self, audio_data: bytes) -> str:
        """Convert audio to text using Google Speech-to-Text API"""
        try:
            # Encode audio as base64
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Prepare request payload
            payload = {
                "config": {
                    "encoding": "WEBM_OPUS",  # Adjust based on audio format
                    "sampleRateHertz": 48000,
                    "languageCode": "pt-BR",
                    "enableAutomaticPunctuation": True,
                    "enableWordTimeOffsets": True,
                    "model": "medical_dictation",  # Medical-specific model
                    "useEnhanced": True,
                    "speechContexts": [{
                        "phrases": list(self.medical_terms.keys()),
                        "boost": 20.0
                    }]
                },
                "audio": {
                    "content": audio_b64
                }
            }
            
            # Make API request
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://speech.googleapis.com/v1/speech:recognize?key={voice_settings.GOOGLE_API_KEY}",
                    json=payload,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if 'results' in result and len(result['results']) > 0:
                        return result['results'][0]['alternatives'][0]['transcript']
                    else:
                        return ""
                else:
                    logger.error(f"Google Speech API error: {response.status_code} - {response.text}")
                    return ""
                    
        except Exception as e:
            logger.error(f"Error with Google Speech-to-Text: {str(e)}")
            return ""
    
    async def _aws_transcribe(self, audio_data: bytes) -> str:
        """Convert audio to text using AWS Transcribe"""
        # Implementation for AWS Transcribe would go here
        # This is a placeholder for future AWS integration
        raise NotImplementedError("AWS Transcribe integration not implemented yet")
    
    def _analyze_medical_terms(self, text: str) -> List[MedicalTerm]:
        """Analyze text for medical terminology"""
        found_terms = []
        text_lower = text.lower()
        
        for term_key, medical_term in self.medical_terms.items():
            if term_key in text_lower:
                found_terms.append(medical_term)
            else:
                # Check synonyms
                for synonym in medical_term.synonyms:
                    if synonym.lower() in text_lower:
                        found_terms.append(medical_term)
                        break
        
        return found_terms
    
    def _extract_voice_commands(self, text: str) -> List[VoiceCommand]:
        """Extract structured voice commands from text"""
        commands = []
        text_lower = text.lower()
        
        # Define command patterns
        command_patterns = {
            VoiceCommandType.SUBJECTIVE: [
                "adicionar queixa", "queixa principal", "história da doença",
                "sintomas", "relato do paciente"
            ],
            VoiceCommandType.OBJECTIVE: [
                "exame físico", "achados do exame", "sinais vitais",
                "inspeção", "palpação", "ausculta", "percussão"
            ],
            VoiceCommandType.ASSESSMENT: [
                "hipótese diagnóstica", "diagnóstico", "impressão diagnóstica",
                "avaliação", "conclusão"
            ],
            VoiceCommandType.PLAN: [
                "conduta", "plano terapêutico", "tratamento", "medicação",
                "exames complementares", "orientações"
            ],
            VoiceCommandType.MEDICATION: [
                "prescrever", "medicamento", "dose", "posologia",
                "antibiótico", "analgésico"
            ],
            VoiceCommandType.VITAL_SIGNS: [
                "pressão arterial", "temperatura", "frequência cardíaca",
                "frequência respiratória", "saturação"
            ]
        }
        
        for cmd_type, patterns in command_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    # Extract content after the command
                    start_idx = text_lower.find(pattern)
                    if start_idx != -1:
                        content_start = start_idx + len(pattern)
                        content = text[content_start:].strip()
                        if content.startswith(':'):
                            content = content[1:].strip()
                        
                        commands.append(VoiceCommand(
                            command_type=cmd_type,
                            content=content,
                            confidence=0.85,  # Default confidence
                            timestamp=datetime.utcnow(),
                            raw_text=text
                        ))
                        break
        
        return commands
    
    def _generate_structured_data(
        self, 
        transcription: str, 
        medical_terms: List[MedicalTerm], 
        commands: List[VoiceCommand]
    ) -> Dict[str, Any]:
        """Generate structured clinical data from voice input"""
        structured = {
            "soap_notes": {
                "subjective": "",
                "objective": "",
                "assessment": "",
                "plan": ""
            },
            "symptoms": [],
            "diagnoses": [],
            "medications": [],
            "vital_signs": {},
            "icd10_codes": [],
            "confidence_scores": {}
        }
        
        # Process commands to populate SOAP sections
        for cmd in commands:
            if cmd.command_type == VoiceCommandType.SUBJECTIVE:
                structured["soap_notes"]["subjective"] += f"{cmd.content}\n"
            elif cmd.command_type == VoiceCommandType.OBJECTIVE:
                structured["soap_notes"]["objective"] += f"{cmd.content}\n"
            elif cmd.command_type == VoiceCommandType.ASSESSMENT:
                structured["soap_notes"]["assessment"] += f"{cmd.content}\n"
            elif cmd.command_type == VoiceCommandType.PLAN:
                structured["soap_notes"]["plan"] += f"{cmd.content}\n"
        
        # Process medical terms
        for term in medical_terms:
            if term.category == "symptom":
                structured["symptoms"].append({
                    "term": term.term,
                    "confidence": term.confidence,
                    "icd10_codes": term.icd10_codes
                })
            elif term.category == "diagnosis":
                structured["diagnoses"].append({
                    "term": term.term,
                    "confidence": term.confidence,
                    "icd10_codes": term.icd10_codes
                })
            
            # Add ICD-10 codes
            structured["icd10_codes"].extend(term.icd10_codes)
        
        # Remove duplicates from ICD-10 codes
        structured["icd10_codes"] = list(set(structured["icd10_codes"]))
        
        return structured
    
    def _calculate_overall_confidence(self, transcription: str, commands: List[VoiceCommand]) -> float:
        """Calculate overall confidence score for the transcription"""
        if not transcription:
            return 0.0
        
        # Base confidence from transcription length and medical terms
        base_confidence = min(len(transcription) / 100, 0.9)  # Max 0.9 for length
        
        # Boost confidence for medical terms
        medical_boost = len(commands) * 0.1
        
        # Boost confidence for command structure
        command_boost = min(len(commands) * 0.05, 0.2)
        
        return min(base_confidence + medical_boost + command_boost, 1.0)
    
    def _encrypt_audio_data(self, audio_data: bytes) -> bytes:
        """Encrypt audio data for HIPAA compliance"""
        fernet = Fernet(self.encryption_key)
        return fernet.encrypt(audio_data)
    
    def _decrypt_audio_data(self, encrypted_data: bytes) -> bytes:
        """Decrypt audio data"""
        fernet = Fernet(self.encryption_key)
        return fernet.decrypt(encrypted_data)
    
    async def _store_audio_session(
        self, 
        session_id: str, 
        encrypted_audio: bytes, 
        user_id: int, 
        appointment_id: int, 
        db: AsyncSession
    ) -> None:
        """Store encrypted audio session data"""
        try:
            # Create or update voice session
            voice_session = VoiceSession(
                session_id=session_id,
                user_id=user_id,
                appointment_id=appointment_id,
                encrypted_audio_data=encrypted_audio,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=24)  # Auto-delete after 24h
            )
            
            db.add(voice_session)
            await db.commit()
            
        except Exception as e:
            logger.error(f"Error storing audio session: {str(e)}")
            await db.rollback()
            raise
    
    async def create_clinical_record_from_voice(
        self,
        session_id: str,
        user_id: int,
        appointment_id: int,
        db: AsyncSession
    ) -> ClinicalRecord:
        """Create clinical record from voice session data"""
        try:
            # Get voice session
            voice_session_query = select(VoiceSession).where(
                VoiceSession.session_id == session_id,
                VoiceSession.user_id == user_id
            )
            voice_session_result = await db.execute(voice_session_query)
            voice_session = voice_session_result.scalar_one_or_none()
            
            if not voice_session:
                raise ValueError("Voice session not found")
            
            # Decrypt and process audio
            decrypted_audio = self._decrypt_audio_data(voice_session.encrypted_audio_data)
            voice_data = await self.process_audio_stream(
                decrypted_audio, user_id, appointment_id, session_id, db
            )
            
            # Create clinical record
            clinical_record = ClinicalRecord(
                appointment_id=appointment_id,
                subjective=voice_data["structured_data"]["soap_notes"]["subjective"],
                objective=voice_data["structured_data"]["soap_notes"]["objective"],
                assessment=voice_data["structured_data"]["soap_notes"]["assessment"],
                plan=voice_data["structured_data"]["soap_notes"]["plan"],
                notes=voice_data["transcription"],
                created_by=user_id,
                created_at=datetime.utcnow()
            )
            
            db.add(clinical_record)
            await db.commit()
            await db.refresh(clinical_record)
            
            return clinical_record
            
        except Exception as e:
            logger.error(f"Error creating clinical note from voice: {str(e)}")
            await db.rollback()
            raise

# Global instance
voice_service = VoiceProcessingService()

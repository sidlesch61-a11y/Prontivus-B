"""
Voice Processing Service for Clinical Documentation
Handles speech-to-text conversion with medical terminology support
"""

import asyncio
import base64
import hashlib
import json
import logging
import re
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
from app.models import User, Patient, Appointment, ClinicalRecord, VoiceSession, AIConfig
from app.models.icd10 import ICD10SearchIndex
from app.services.ai_service import create_ai_service, AIServiceError
from app.services.encryption_service import decrypt
from app.services.icd10_import import normalize_text

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
            # Get user and appointment to access clinic_id
            user_query = select(User).where(User.id == user_id)
            user_result = await db.execute(user_query)
            user = user_result.scalar_one_or_none()
            clinic_id = user.clinic_id if user else None
            
            # Encrypt audio data for HIPAA compliance
            encrypted_audio = self._encrypt_audio_data(audio_data)
            
            # Store encrypted audio temporarily
            await self._store_audio_session(session_id, encrypted_audio, user_id, appointment_id, db)
            
            # Convert speech to text (with AI if available)
            transcription = await self._speech_to_text(audio_data, clinic_id, db)
            
            # Process medical terminology (with AI + ICD-10 search)
            medical_analysis = await self._analyze_medical_terms(transcription, clinic_id, db)
            
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
    
    async def _speech_to_text(self, audio_data: bytes, clinic_id: Optional[int] = None, db: Optional[AsyncSession] = None) -> str:
        """
        Convert audio to text using AI service if available, otherwise fallback to Google Speech API
        
        Args:
            audio_data: Raw audio bytes
            clinic_id: Clinic ID to check for AI configuration
            db: Database session
            
        Returns:
            Transcribed text
        """
        # Try to use AI service if configured
        if clinic_id and db:
            try:
                ai_transcription = await self._ai_speech_to_text(audio_data, clinic_id, db)
                if ai_transcription:
                    return ai_transcription
            except Exception as e:
                logger.warning(f"AI transcription failed, falling back to Google Speech: {str(e)}")
        
        # Fallback to Google Speech API
        if self.voice_provider == VoiceProvider.GOOGLE:
            return await self._google_speech_to_text(audio_data)
        elif self.voice_provider == VoiceProvider.AWS:
            return await self._aws_transcribe(audio_data)
        else:
            raise ValueError(f"Unsupported voice provider: {self.voice_provider}")
    
    async def _ai_speech_to_text(self, audio_data: bytes, clinic_id: int, db: AsyncSession) -> Optional[str]:
        """
        Convert audio to text using AI service (for transcription enhancement)
        Note: AI services typically don't handle raw audio directly, so we use Google Speech first
        then enhance with AI, or use AI to improve the transcription quality
        
        Args:
            audio_data: Raw audio bytes
            clinic_id: Clinic ID
            db: Database session
            
        Returns:
            Enhanced transcription or None if AI not available
        """
        try:
            # Get AI config for clinic
            ai_config_query = select(AIConfig).where(
                AIConfig.clinic_id == clinic_id,
                AIConfig.enabled == True
            )
            ai_config_result = await db.execute(ai_config_query)
            ai_config = ai_config_result.scalar_one_or_none()
            
            if not ai_config or not ai_config.api_key_encrypted:
                return None
            
            # First, get basic transcription from Google Speech (AI services don't handle raw audio well)
            basic_transcription = await self._google_speech_to_text(audio_data)
            
            if not basic_transcription:
                return None
            
            # Enhance transcription with AI for medical context
            ai_service = create_ai_service(
                provider=ai_config.provider,
                api_key_encrypted=ai_config.api_key_encrypted,
                model=ai_config.model or "gpt-4",
                base_url=ai_config.base_url,
                max_tokens=ai_config.max_tokens,
                temperature=ai_config.temperature
            )
            
            # Use AI to improve medical transcription
            system_prompt = """You are a medical transcription assistant. Improve the following medical transcription 
            for accuracy, especially for medical terminology. Return only the improved transcription without additional comments."""
            
            prompt = f"Improve this medical transcription for accuracy:\n\n{basic_transcription}"
            
            enhanced_transcription, usage = await ai_service.generate_completion(
                prompt=prompt,
                system_prompt=system_prompt
            )
            
            # Update token usage (handled by AI service internally)
            logger.info(f"AI transcription enhancement used {usage.get('tokens_used', 0)} tokens")
            
            return enhanced_transcription.strip()
            
        except AIServiceError as e:
            logger.warning(f"AI service error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error in AI transcription: {str(e)}")
            return None
    
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
    
    async def _analyze_medical_terms(self, text: str, clinic_id: Optional[int] = None, db: Optional[AsyncSession] = None) -> List[MedicalTerm]:
        """
        Analyze text for medical terminology using AI and ICD-10 database
        
        Args:
            text: Transcription text
            clinic_id: Clinic ID for AI configuration
            db: Database session for ICD-10 search
            
        Returns:
            List of medical terms with ICD-10 codes
        """
        found_terms = []
        text_lower = text.lower()
        
        # First, check hardcoded dictionary (quick lookup)
        for term_key, medical_term in self.medical_terms.items():
            if term_key in text_lower:
                found_terms.append(medical_term)
            else:
                # Check synonyms
                for synonym in medical_term.synonyms:
                    if synonym.lower() in text_lower:
                        found_terms.append(medical_term)
                        break
        
        # Use AI to extract additional medical terms if available
        if clinic_id and db and text.strip():
            try:
                ai_terms = await self._ai_extract_medical_terms(text, clinic_id, db)
                found_terms.extend(ai_terms)
            except Exception as e:
                logger.warning(f"AI medical term extraction failed: {str(e)}")
        
        # Query ICD-10 database for code suggestions
        if db and text.strip():
            try:
                icd10_suggestions = await self._get_icd10_suggestions(text, db)
                # Convert ICD-10 suggestions to MedicalTerm objects
                for suggestion in icd10_suggestions:
                    # Check if we already have this term
                    existing = next((t for t in found_terms if suggestion['code'] in t.icd10_codes), None)
                    if not existing:
                        found_terms.append(MedicalTerm(
                            term=suggestion.get('description', ''),
                            category="diagnosis",
                            icd10_codes=[suggestion['code']],
                            synonyms=[],
                            confidence=0.85
                        ))
            except Exception as e:
                logger.warning(f"ICD-10 search failed: {str(e)}")
        
        # Remove duplicates
        seen = set()
        unique_terms = []
        for term in found_terms:
            term_key = (term.term.lower(), tuple(sorted(term.icd10_codes)))
            if term_key not in seen:
                seen.add(term_key)
                unique_terms.append(term)
        
        return unique_terms
    
    async def _ai_extract_medical_terms(self, text: str, clinic_id: int, db: AsyncSession) -> List[MedicalTerm]:
        """
        Use AI to extract medical terms from transcription
        
        Args:
            text: Transcription text
            clinic_id: Clinic ID
            db: Database session
            
        Returns:
            List of MedicalTerm objects
        """
        try:
            # Get AI config
            ai_config_query = select(AIConfig).where(
                AIConfig.clinic_id == clinic_id,
                AIConfig.enabled == True
            )
            ai_config_result = await db.execute(ai_config_query)
            ai_config = ai_config_result.scalar_one_or_none()
            
            if not ai_config or not ai_config.api_key_encrypted:
                return []
            
            # Create AI service
            ai_service = create_ai_service(
                provider=ai_config.provider,
                api_key_encrypted=ai_config.api_key_encrypted,
                model=ai_config.model or "gpt-4",
                base_url=ai_config.base_url,
                max_tokens=ai_config.max_tokens,
                temperature=ai_config.temperature
            )
            
            # Prompt AI to extract medical terms
            system_prompt = """You are a medical AI assistant. Extract medical terms (symptoms, diagnoses, medications) 
            from the transcription. Return a JSON array with objects containing: "term", "category" (symptom/diagnosis/medication), 
            and "confidence" (0.0-1.0)."""
            
            prompt = f"Extract medical terms from this transcription:\n\n{text}\n\nReturn only the JSON array."
            
            response, usage = await ai_service.generate_completion(
                prompt=prompt,
                system_prompt=system_prompt
            )
            
            # Parse AI response
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                ai_terms_data = json.loads(json_match.group())
                
                # Convert to MedicalTerm objects
                medical_terms = []
                for term_data in ai_terms_data:
                    term_text = term_data.get('term', '').lower()
                    if term_text:
                        # Search ICD-10 for this term
                        icd10_codes = await self._search_icd10_for_term(term_text, db)
                        
                        medical_terms.append(MedicalTerm(
                            term=term_data.get('term', ''),
                            category=term_data.get('category', 'symptom'),
                            icd10_codes=icd10_codes,
                            synonyms=[],
                            confidence=float(term_data.get('confidence', 0.8))
                        ))
                
                return medical_terms
            
            return []
            
        except Exception as e:
            logger.error(f"Error in AI medical term extraction: {str(e)}")
            return []
    
    async def _get_icd10_suggestions(self, text: str, db: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get ICD-10 code suggestions from database based on transcription
        
        Args:
            text: Transcription text
            db: Database session
            limit: Maximum number of suggestions
            
        Returns:
            List of ICD-10 suggestions with code and description
        """
        try:
            # Extract key medical terms from text (simple keyword extraction)
            words = text.lower().split()
            medical_keywords = [w for w in words if len(w) > 4]  # Filter short words
            
            suggestions = []
            seen_codes = set()
            
            # Search for each keyword in ICD-10 database
            for keyword in medical_keywords[:5]:  # Limit to 5 keywords to avoid too many queries
                normalized = normalize_text(keyword)
                query = select(ICD10SearchIndex).filter(
                    ICD10SearchIndex.search_text.ilike(f"%{normalized}%")
                ).limit(limit)
                
                results = (await db.execute(query)).scalars().all()
                
                for result in results:
                    if result.code not in seen_codes:
                        seen_codes.add(result.code)
                        suggestions.append({
                            "code": result.code,
                            "description": result.description,
                            "level": result.level,
                            "confidence": 0.8  # Default confidence
                        })
                        
                        if len(suggestions) >= limit:
                            break
                
                if len(suggestions) >= limit:
                    break
            
            return suggestions[:limit]
            
        except Exception as e:
            logger.error(f"Error getting ICD-10 suggestions: {str(e)}")
            return []
    
    async def _search_icd10_for_term(self, term: str, db: AsyncSession, limit: int = 3) -> List[str]:
        """
        Search ICD-10 database for a specific medical term
        
        Args:
            term: Medical term to search
            db: Database session
            limit: Maximum number of codes to return
            
        Returns:
            List of ICD-10 codes
        """
        try:
            normalized = normalize_text(term)
            query = select(ICD10SearchIndex).filter(
                ICD10SearchIndex.search_text.ilike(f"%{normalized}%")
            ).limit(limit)
            
            results = (await db.execute(query)).scalars().all()
            return [r.code for r in results]
            
        except Exception as e:
            logger.error(f"Error searching ICD-10 for term '{term}': {str(e)}")
            return []
    
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

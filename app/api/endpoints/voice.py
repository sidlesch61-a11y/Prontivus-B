"""
Voice Processing API Endpoints
Handles voice-to-text clinical documentation
"""

import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_async_session
from app.core.auth import get_current_user
from app.models import User, Appointment, VoiceSession, VoiceCommand, MedicalTerm, VoiceConfiguration
from app.schemas.voice import (
    VoiceSessionCreate, VoiceSessionResponse, VoiceCommandResponse,
    MedicalTermResponse, VoiceConfigurationResponse, VoiceProcessingResult
)
from app.services.voice_processing import voice_service

router = APIRouter(tags=["Voice Processing"])

@router.post("/voice/process", response_model=VoiceProcessingResult)
async def process_voice_audio(
    audio_file: UploadFile = File(...),
    appointment_id: int = Form(...),
    session_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Process voice audio and return transcription with medical analysis
    
    Args:
        audio_file: Audio file (WAV, MP3, or WebM format)
        appointment_id: ID of the appointment
        session_id: Optional session ID for tracking
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Voice processing result with transcription and medical analysis
    """
    try:
        # Verify appointment exists and user has access
        appointment_query = select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.doctor_id == current_user.id
        )
        appointment_result = await db.execute(appointment_query)
        appointment = appointment_result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found or access denied"
            )
        
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Read audio file
        audio_data = await audio_file.read()
        
        # Process voice audio
        result = await voice_service.process_audio_stream(
            audio_data=audio_data,
            user_id=current_user.id,
            appointment_id=appointment_id,
            session_id=session_id,
            db=db
        )
        
        return VoiceProcessingResult(**result)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing voice audio: {str(e)}"
        )

@router.post("/voice/sessions", response_model=VoiceSessionResponse)
async def create_voice_session(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new voice session for an appointment
    
    Args:
        appointment_id: ID of the appointment
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Voice session information
    """
    try:
        # Verify appointment exists and user has access
        appointment_query = select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.doctor_id == current_user.id
        )
        appointment_result = await db.execute(appointment_query)
        appointment = appointment_result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found or access denied"
            )
        
        # Create voice session
        session_id = str(uuid.uuid4())
        voice_session = VoiceSession(
            session_id=session_id,
            user_id=current_user.id,
            appointment_id=appointment_id,
            encrypted_audio_data=b"",  # Empty initially
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        db.add(voice_session)
        await db.commit()
        await db.refresh(voice_session)
        
        return VoiceSessionResponse(
            session_id=voice_session.session_id,
            appointment_id=voice_session.appointment_id,
            created_at=voice_session.created_at,
            expires_at=voice_session.expires_at
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating voice session: {str(e)}"
        )

@router.get("/voice/sessions/{session_id}", response_model=VoiceSessionResponse)
async def get_voice_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get voice session information
    
    Args:
        session_id: Voice session ID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Voice session information
    """
    try:
        voice_session_query = select(VoiceSession).where(
            VoiceSession.session_id == session_id,
            VoiceSession.user_id == current_user.id
        )
        voice_session_result = await db.execute(voice_session_query)
        voice_session = voice_session_result.scalar_one_or_none()
        
        if not voice_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Voice session not found"
            )
        
        return VoiceSessionResponse(
            session_id=voice_session.session_id,
            appointment_id=voice_session.appointment_id,
            created_at=voice_session.created_at,
            expires_at=voice_session.expires_at
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving voice session: {str(e)}"
        )

@router.get("/voice/sessions", response_model=List[VoiceSessionResponse])
async def list_voice_sessions(
    appointment_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List voice sessions for the current user
    
    Args:
        appointment_id: Optional appointment ID filter
        limit: Maximum number of sessions to return
        offset: Number of sessions to skip
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        List of voice sessions
    """
    try:
        query = select(VoiceSession).where(VoiceSession.user_id == current_user.id)
        
        if appointment_id:
            query = query.where(VoiceSession.appointment_id == appointment_id)
        
        query = query.offset(offset).limit(limit).order_by(VoiceSession.created_at.desc())
        
        result = await db.execute(query)
        voice_sessions = result.scalars().all()
        
        return [
            VoiceSessionResponse(
                session_id=session.session_id,
                appointment_id=session.appointment_id,
                created_at=session.created_at,
                expires_at=session.expires_at
            )
            for session in voice_sessions
        ]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing voice sessions: {str(e)}"
        )

@router.post("/voice/sessions/{session_id}/create-note")
async def create_clinical_note_from_voice(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a clinical note from voice session data
    
    Args:
        session_id: Voice session ID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Created clinical note information
    """
    try:
        # Get voice session
        voice_session_query = select(VoiceSession).where(
            VoiceSession.session_id == session_id,
            VoiceSession.user_id == current_user.id
        )
        voice_session_result = await db.execute(voice_session_query)
        voice_session = voice_session_result.scalar_one_or_none()
        
        if not voice_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Voice session not found"
            )
        
        # Create clinical record from voice data
        clinical_record = await voice_service.create_clinical_record_from_voice(
            session_id=session_id,
            user_id=current_user.id,
            appointment_id=voice_session.appointment_id,
            db=db
        )
        
        return {
            "message": "Clinical record created successfully",
            "record_id": clinical_record.id,
            "appointment_id": clinical_record.appointment_id,
            "created_at": clinical_record.created_at
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating clinical note: {str(e)}"
        )

@router.get("/voice/medical-terms", response_model=List[MedicalTermResponse])
async def get_medical_terms(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get medical terms for voice processing
    
    Args:
        category: Optional category filter (symptom, diagnosis, medication, etc.)
        search: Optional search term
        limit: Maximum number of terms to return
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        List of medical terms
    """
    try:
        query = select(MedicalTerm)
        
        if category:
            query = query.where(MedicalTerm.category == category)
        
        if search:
            query = query.where(MedicalTerm.term.ilike(f"%{search}%"))
        
        query = query.limit(limit).order_by(MedicalTerm.term)
        
        result = await db.execute(query)
        medical_terms = result.scalars().all()
        
        return [
            MedicalTermResponse(
                id=term.id,
                term=term.term,
                category=term.category,
                icd10_codes=term.icd10_codes.split(',') if term.icd10_codes else [],
                synonyms=term.synonyms.split(',') if term.synonyms else [],
                confidence=term.confidence,
                language=term.language
            )
            for term in medical_terms
        ]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving medical terms: {str(e)}"
        )

@router.get("/voice/configuration", response_model=VoiceConfigurationResponse)
async def get_voice_configuration(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get voice processing configuration for the current user
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Voice configuration
    """
    try:
        # Try to get user-specific configuration
        config_query = select(VoiceConfiguration).where(
            VoiceConfiguration.user_id == current_user.id
        )
        config_result = await db.execute(config_query)
        config = config_result.scalar_one_or_none()
        
        # If no user config, try clinic config
        if not config:
            config_query = select(VoiceConfiguration).where(
                VoiceConfiguration.clinic_id == current_user.clinic_id
            )
            config_result = await db.execute(config_query)
            config = config_result.scalar_one_or_none()
        
        # If no config found, return default
        if not config:
            return VoiceConfigurationResponse(
                provider="google",
                language="pt-BR",
                model="medical_dictation",
                enable_auto_punctuation=True,
                enable_word_time_offsets=True,
                confidence_threshold=0.8,
                enable_icd10_suggestions=True,
                enable_medication_recognition=True,
                auto_delete_after_hours=24,
                enable_encryption=True,
                enable_audit_logging=True
            )
        
        return VoiceConfigurationResponse(
            provider=config.provider,
            language=config.language,
            model=config.model,
            enable_auto_punctuation=config.enable_auto_punctuation == "true",
            enable_word_time_offsets=config.enable_word_time_offsets == "true",
            confidence_threshold=float(config.confidence_threshold),
            enable_icd10_suggestions=config.enable_icd10_suggestions == "true",
            enable_medication_recognition=config.enable_medication_recognition == "true",
            auto_delete_after_hours=config.auto_delete_after_hours,
            enable_encryption=config.enable_encryption == "true",
            enable_audit_logging=config.enable_audit_logging == "true"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving voice configuration: {str(e)}"
        )

@router.delete("/voice/sessions/{session_id}")
async def delete_voice_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Delete a voice session and its associated data
    
    Args:
        session_id: Voice session ID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Success message
    """
    try:
        voice_session_query = select(VoiceSession).where(
            VoiceSession.session_id == session_id,
            VoiceSession.user_id == current_user.id
        )
        voice_session_result = await db.execute(voice_session_query)
        voice_session = voice_session_result.scalar_one_or_none()
        
        if not voice_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Voice session not found"
            )
        
        # Delete associated voice commands
        commands_query = select(VoiceCommand).where(
            VoiceCommand.session_id == session_id
        )
        commands_result = await db.execute(commands_query)
        commands = commands_result.scalars().all()
        
        for command in commands:
            await db.delete(command)
        
        # Delete voice session
        await db.delete(voice_session)
        await db.commit()
        
        return {"message": "Voice session deleted successfully"}
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting voice session: {str(e)}"
        )

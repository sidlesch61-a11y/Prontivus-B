"""
Message API endpoints for patient-provider communication
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from sqlalchemy.orm import joinedload, selectinload

from app.core.auth import get_current_user, RoleChecker
from app.models import User, Patient, UserRole
from app.models.message import MessageThread, Message, MessageStatus
from app.schemas.message import (
    MessageCreate,
    MessageResponse,
    MessageThreadCreate,
    MessageThreadResponse,
    MessageThreadDetailResponse,
)
from database import get_async_session
import datetime

router = APIRouter(prefix="/messages", tags=["Messages"])

# Allow both patients and staff to access messages
require_authenticated = RoleChecker([UserRole.PATIENT, UserRole.DOCTOR, UserRole.SECRETARY, UserRole.ADMIN])


@router.get("/threads", response_model=List[MessageThreadResponse])
async def list_threads(
    current_user: User = Depends(require_authenticated),
    db: AsyncSession = Depends(get_async_session),
    archived: bool = False,
):
    """
    List all message threads for the current user
    Patients see threads where they are the patient
    Staff see threads where they are the provider
    """
    # Determine if user is a patient
    patient_query = select(Patient).filter(
        and_(
            Patient.email == current_user.email,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    
    if patient:
        # User is a patient - get threads where patient_id matches
        query = select(MessageThread).filter(
            and_(
                MessageThread.patient_id == patient.id,
                MessageThread.clinic_id == current_user.clinic_id,
                MessageThread.is_archived == archived
            )
        ).options(
            joinedload(MessageThread.provider),
            selectinload(MessageThread.messages)
        ).order_by(MessageThread.last_message_at.desc().nullslast(), MessageThread.created_at.desc())
    else:
        # User is staff - get threads where provider_id matches
        query = select(MessageThread).filter(
            and_(
                MessageThread.provider_id == current_user.id,
                MessageThread.clinic_id == current_user.clinic_id,
                MessageThread.is_archived == archived
            )
        ).options(
            joinedload(MessageThread.patient),
            selectinload(MessageThread.messages)
        ).order_by(MessageThread.last_message_at.desc().nullslast(), MessageThread.created_at.desc())
    
    result = await db.execute(query)
    threads = result.scalars().unique().all()
    
    # Build response with unread count and last message
    response = []
    for thread in threads:
        # Count unread messages
        if patient:
            unread_query = select(func.count(Message.id)).filter(
                and_(
                    Message.thread_id == thread.id,
                    Message.sender_type != "patient",
                    Message.status != MessageStatus.READ
                )
            )
        else:
            unread_query = select(func.count(Message.id)).filter(
                and_(
                    Message.thread_id == thread.id,
                    Message.sender_type == "patient",
                    Message.status != MessageStatus.READ
                )
            )
        unread_result = await db.execute(unread_query)
        unread_count = unread_result.scalar() or 0
        
        # Get last message
        last_msg_query = select(Message).filter(
            Message.thread_id == thread.id
        ).order_by(Message.created_at.desc()).limit(1)
        last_msg_result = await db.execute(last_msg_query)
        last_message = last_msg_result.scalar_one_or_none()
        
        # Get provider name
        if patient:
            provider_name = f"{thread.provider.first_name} {thread.provider.last_name}" if thread.provider else "Unknown"
            provider_specialty = None
        else:
            provider_name = f"{current_user.first_name} {current_user.last_name}"
            provider_specialty = None
        
        response.append(MessageThreadResponse(
            id=thread.id,
            patient_id=thread.patient_id,
            provider_id=thread.provider_id,
            provider_name=provider_name,
            provider_specialty=provider_specialty,
            topic=thread.topic,
            is_urgent=thread.is_urgent,
            is_archived=thread.is_archived,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            last_message_at=last_message.created_at if last_message else None,
            last_message=last_message.content[:100] if last_message else None,
            unread_count=unread_count,
        ))
    
    return response


@router.get("/threads/{thread_id}", response_model=MessageThreadDetailResponse)
async def get_thread(
    thread_id: int,
    current_user: User = Depends(require_authenticated),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get a specific thread with all messages
    """
    # Check if user has access to this thread
    patient_query = select(Patient).filter(
        and_(
            Patient.email == current_user.email,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    
    query = select(MessageThread).filter(
        MessageThread.id == thread_id
    ).options(
        joinedload(MessageThread.provider),
        joinedload(MessageThread.patient),
        selectinload(MessageThread.messages)
    )
    
    result = await db.execute(query)
    thread = result.scalar_one_or_none()
    
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Check access
    if patient:
        if thread.patient_id != patient.id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if thread.provider_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Count unread
    if patient:
        unread_query = select(func.count(Message.id)).filter(
            and_(
                Message.thread_id == thread.id,
                Message.sender_type != "patient",
                Message.status != MessageStatus.READ
            )
        )
    else:
        unread_query = select(func.count(Message.id)).filter(
            and_(
                Message.thread_id == thread.id,
                Message.sender_type == "patient",
                Message.status != MessageStatus.READ
            )
        )
    unread_result = await db.execute(unread_query)
    unread_count = unread_result.scalar() or 0
    
    # Get last message
    last_msg_query = select(Message).filter(
        Message.thread_id == thread.id
    ).order_by(Message.created_at.desc()).limit(1)
    last_msg_result = await db.execute(last_msg_query)
    last_message = last_msg_result.scalar_one_or_none()
    
    # Get provider name
    if patient:
        provider_name = f"{thread.provider.first_name} {thread.provider.last_name}" if thread.provider else "Unknown"
        provider_specialty = None
    else:
        provider_name = f"{current_user.first_name} {current_user.last_name}"
        provider_specialty = None
    
    # Mark messages as read
    from sqlalchemy import update
    if patient:
        # Mark provider messages as read
        await db.execute(
            update(Message).where(
                and_(
                    Message.thread_id == thread.id,
                    Message.sender_type != "patient",
                    Message.status != MessageStatus.READ
                )
            ).values(status=MessageStatus.READ, read_at=datetime.datetime.now())
        )
    else:
        # Mark patient messages as read
        await db.execute(
            update(Message).where(
                and_(
                    Message.thread_id == thread.id,
                    Message.sender_type == "patient",
                    Message.status != MessageStatus.READ
                )
            ).values(status=MessageStatus.READ, read_at=datetime.datetime.now())
        )
    await db.commit()
    
    return MessageThreadDetailResponse(
        id=thread.id,
        patient_id=thread.patient_id,
        provider_id=thread.provider_id,
        provider_name=provider_name,
        provider_specialty=provider_specialty,
        topic=thread.topic,
        is_urgent=thread.is_urgent,
        is_archived=thread.is_archived,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        last_message_at=last_message.created_at if last_message else None,
        last_message=last_message.content[:100] if last_message else None,
        unread_count=unread_count,
        messages=[MessageResponse.model_validate(msg) for msg in sorted(thread.messages, key=lambda m: m.created_at)],
    )


@router.post("/threads", response_model=MessageThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(
    thread_in: MessageThreadCreate,
    current_user: User = Depends(require_authenticated),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new message thread
    Patients can create threads with providers
    """
    # Find patient
    patient_query = select(Patient).filter(
        and_(
            Patient.email == current_user.email,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    
    # Verify provider exists and belongs to same clinic
    provider_query = select(User).filter(
        and_(
            User.id == thread_in.provider_id,
            User.clinic_id == current_user.clinic_id,
            User.role.in_([UserRole.DOCTOR, UserRole.SECRETARY, UserRole.ADMIN])
        )
    )
    provider_result = await db.execute(provider_query)
    provider = provider_result.scalar_one_or_none()
    
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    # Check if thread already exists
    existing_query = select(MessageThread).filter(
        and_(
            MessageThread.patient_id == patient.id,
            MessageThread.provider_id == thread_in.provider_id,
            MessageThread.clinic_id == current_user.clinic_id,
            MessageThread.is_archived == False
        )
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        # Return existing thread
        return MessageThreadResponse(
            id=existing.id,
            patient_id=existing.patient_id,
            provider_id=existing.provider_id,
            provider_name=f"{provider.first_name} {provider.last_name}",
            provider_specialty=None,
            topic=existing.topic,
            is_urgent=existing.is_urgent,
            is_archived=existing.is_archived,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
            last_message_at=existing.last_message_at,
            last_message=None,
            unread_count=0,
        )
    
    # Create new thread
    thread = MessageThread(
        patient_id=patient.id,
        provider_id=thread_in.provider_id,
        topic=thread_in.topic,
        is_urgent=thread_in.is_urgent,
        clinic_id=current_user.clinic_id,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    
    return MessageThreadResponse(
        id=thread.id,
        patient_id=thread.patient_id,
        provider_id=thread.provider_id,
        provider_name=f"{provider.first_name} {provider.last_name}",
        provider_specialty=None,
        topic=thread.topic,
        is_urgent=thread.is_urgent,
        is_archived=thread.is_archived,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        last_message_at=None,
        last_message=None,
        unread_count=0,
    )


@router.post("/threads/{thread_id}/send", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    thread_id: int,
    message_in: MessageCreate,
    current_user: User = Depends(require_authenticated),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Send a message in a thread
    """
    # Verify thread exists and user has access
    patient_query = select(Patient).filter(
        and_(
            Patient.email == current_user.email,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    
    query = select(MessageThread).filter(MessageThread.id == thread_id)
    result = await db.execute(query)
    thread = result.scalar_one_or_none()
    
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Check access
    if patient:
        if thread.patient_id != patient.id:
            raise HTTPException(status_code=403, detail="Access denied")
        sender_type = "patient"
    else:
        if thread.provider_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        sender_type = "provider"
    
    # Create message
    message = Message(
        thread_id=thread_id,
        sender_id=current_user.id,
        sender_type=sender_type,
        content=message_in.content,
        attachments=message_in.attachments,
        medical_context=message_in.medical_context,
        status=MessageStatus.SENT,
    )
    db.add(message)
    
    # Update thread last_message_at
    thread.last_message_at = datetime.datetime.now()
    
    await db.commit()
    await db.refresh(message)
    
    return MessageResponse.model_validate(message)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: int,
    current_user: User = Depends(require_authenticated),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Archive (soft delete) a thread
    """
    # Verify thread exists and user has access
    patient_query = select(Patient).filter(
        and_(
            Patient.email == current_user.email,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    
    query = select(MessageThread).filter(MessageThread.id == thread_id)
    result = await db.execute(query)
    thread = result.scalar_one_or_none()
    
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Check access
    if patient:
        if thread.patient_id != patient.id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if thread.provider_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Archive thread
    thread.is_archived = True
    await db.commit()
    
    return None


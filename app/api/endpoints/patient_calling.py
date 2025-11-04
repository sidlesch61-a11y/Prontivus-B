from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone
import traceback
import logging

logger = logging.getLogger(__name__)

from database import get_async_session
from app.core.auth import get_current_user
from app.models import User, Appointment, Patient, PatientCall
from app.schemas.patient_call import PatientCallResponse, PatientCallCreate, PatientCallUpdate
from app.api.endpoints.websocket_calling import broadcast_call_to_clinic, broadcast_status_update, broadcast_call_removed

router = APIRouter(prefix="/patient-calling", tags=["Patient Calling"])


@router.post("/call", response_model=PatientCallResponse)
async def call_patient(
    data: PatientCallCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Call a patient for consultation"""
    try:
        if current_user.role not in ["doctor", "admin"]:
            raise HTTPException(status_code=403, detail="Apenas médicos podem chamar pacientes")
        
        # Get appointment details
        appointment_stmt = select(Appointment).where(Appointment.id == data.appointment_id)
        appointment_result = await db.execute(appointment_stmt)
        appointment = appointment_result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Agendamento não encontrado")
        
        if appointment.doctor_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Apenas o médico do agendamento pode chamar o paciente")
        
        # Get patient details
        patient_stmt = select(Patient).where(Patient.id == appointment.patient_id)
        patient_result = await db.execute(patient_stmt)
        patient = patient_result.scalar_one_or_none()
        
        if not patient:
            raise HTTPException(status_code=404, detail="Paciente não encontrado")
        
        # Extract all values from ORM objects BEFORE any potential rollback
        appointment_id = appointment.id
        patient_id = appointment.patient_id
        patient_name = f"{patient.first_name} {patient.last_name}"
        doctor_id = current_user.id
        doctor_name = f"{current_user.first_name} {current_user.last_name}"
        clinic_id = current_user.clinic_id
        
        # Use in-memory storage if table doesn't exist (fallback)
        called_at = datetime.now(timezone.utc)
        
        try:
            # Create or update call record
            call_stmt = select(PatientCall).where(PatientCall.appointment_id == data.appointment_id)
            call_result = await db.execute(call_stmt)
            existing_call = call_result.scalar_one_or_none()
            
            if existing_call:
                existing_call.status = "called"
                existing_call.called_at = called_at
                call_record = existing_call
            else:
                call_record = PatientCall(
                    appointment_id=data.appointment_id,
                    patient_id=patient_id,
                    doctor_id=doctor_id,
                    clinic_id=clinic_id,
                    status="called",
                    called_at=called_at,
                )
                db.add(call_record)
            
            await db.commit()
            await db.refresh(call_record)
            call_id = call_record.id
        except SQLAlchemyError as e:
            # Table might not exist yet - use in-memory fallback
            logger.warning(f"Database error (table may not exist): {e}")
            await db.rollback()
            call_id = appointment_id  # Use appointment_id as temporary ID
        
        # Broadcast via WebSocket
        call_data = {
            "id": call_id,
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "clinic_id": clinic_id,
            "status": "called",
            "called_at": called_at.isoformat(),
        }
        # Store in active calls
        from app.services.socket_manager import active_calls
        active_calls[appointment_id] = call_data
        await broadcast_call_to_clinic(clinic_id, call_data)
        
        return PatientCallResponse(
            id=call_id,
            appointment_id=appointment_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            clinic_id=clinic_id,
            status="called",
            called_at=called_at,
            answered_at=None,
            patient_name=patient_name,
            doctor_name=doctor_name,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calling patient: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao chamar paciente: {str(e)}"
        )


@router.post("/answer/{appointment_id}")
async def answer_call(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Mark call as answered (patient arrived)"""
    call_stmt = select(PatientCall).where(PatientCall.appointment_id == appointment_id)
    call_result = await db.execute(call_stmt)
    call_record = call_result.scalar_one_or_none()
    
    if not call_record:
        raise HTTPException(status_code=404, detail="Chamada não encontrada")
    
    call_record.status = "answered"
    call_record.answered_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    # Broadcast status update
    from app.services.socket_manager import active_calls
    if appointment_id in active_calls:
        active_calls[appointment_id]['status'] = "answered"
    await broadcast_status_update(call_record.clinic_id, appointment_id, "answered")
    
    return {"status": "answered", "appointment_id": appointment_id}


@router.post("/complete/{appointment_id}")
async def complete_call(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Mark call as completed"""
    call_stmt = select(PatientCall).where(PatientCall.appointment_id == appointment_id)
    call_result = await db.execute(call_stmt)
    call_record = call_result.scalar_one_or_none()
    
    if not call_record:
        raise HTTPException(status_code=404, detail="Chamada não encontrada")
    
    call_record.status = "completed"
    call_record.completed_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    # Remove from active calls and broadcast
    from app.services.socket_manager import active_calls
    if appointment_id in active_calls:
        del active_calls[appointment_id]
    await broadcast_call_removed(call_record.clinic_id, appointment_id)
    
    return {"status": "completed", "appointment_id": appointment_id}


@router.get("/active", response_model=list[PatientCallResponse])
async def get_active_calls(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get active calls for the clinic"""
    try:
        # Get calls from last 5 minutes
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        
        calls_stmt = (
            select(PatientCall)
            .where(
                PatientCall.clinic_id == current_user.clinic_id,
                PatientCall.called_at >= cutoff,
                PatientCall.status.in_(["called", "answered"])
            )
            .order_by(PatientCall.called_at.desc())
        )
        
        calls_result = await db.execute(calls_stmt)
        calls = calls_result.scalars().all()
        
        # Enrich with patient and doctor names
        result = []
        for call in calls:
            # Get patient
            patient_stmt = select(Patient).where(Patient.id == call.patient_id)
            patient_result = await db.execute(patient_stmt)
            patient = patient_result.scalar_one_or_none()
            
            # Get doctor
            doctor_stmt = select(User).where(User.id == call.doctor_id)
            doctor_result = await db.execute(doctor_stmt)
            doctor = doctor_result.scalar_one_or_none()
            
            result.append(PatientCallResponse(
                id=call.id,
                appointment_id=call.appointment_id,
                patient_id=call.patient_id,
                doctor_id=call.doctor_id,
                clinic_id=call.clinic_id,
                status=call.status,
                called_at=call.called_at,
                answered_at=call.answered_at,
                patient_name=f"{patient.first_name} {patient.last_name}" if patient else None,
                doctor_name=f"{doctor.first_name} {doctor.last_name}" if doctor else None,
            ))
        
        return result
    except SQLAlchemyError as e:
        # Table might not exist - return from in-memory storage
        logger.warning(f"Database error in get_active_calls: {e}")
        from app.services.socket_manager import active_calls
        return [
            PatientCallResponse(
                id=call_data.get("id", call_data["appointment_id"]),
                appointment_id=call_data["appointment_id"],
                patient_id=call_data["patient_id"],
                doctor_id=call_data["doctor_id"],
                clinic_id=call_data["clinic_id"],
                status=call_data["status"],
                called_at=datetime.fromisoformat(call_data["called_at"].replace('Z', '+00:00')),
                answered_at=datetime.fromisoformat(call_data["answered_at"].replace('Z', '+00:00')) if call_data.get("answered_at") else None,
                patient_name=call_data.get("patient_name"),
                doctor_name=call_data.get("doctor_name"),
            )
            for call_data in active_calls.values()
            if call_data.get("clinic_id") == current_user.clinic_id
        ]


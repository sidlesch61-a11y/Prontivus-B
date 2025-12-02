"""
Appointment management API endpoints
"""
import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.core.auth import get_current_user, RoleChecker
from app.models import User, Appointment, Patient, UserRole, AppointmentStatus
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentResponse,
    AppointmentListResponse,
    AppointmentStatusUpdate,
)
from pydantic import BaseModel
from database import get_async_session
from app.services.realtime import appointment_realtime_manager

router = APIRouter(prefix="/appointments", tags=["Appointments"])

# Role checker for staff (admin, secretary, doctor)
require_staff = RoleChecker([UserRole.ADMIN, UserRole.SECRETARY, UserRole.DOCTOR])


class TodayPatientResponse(BaseModel):
  appointment_id: int
  patient_id: int
  patient_name: str
  doctor_id: int
  doctor_name: str
  scheduled_datetime: datetime.datetime



async def check_slot_availability(
    db: AsyncSession,
    doctor_id: int,
    scheduled_datetime: datetime.datetime,
    clinic_id: int,
    exclude_appointment_id: Optional[int] = None,
    duration_minutes: int = 30,
) -> bool:
    """
    Check if a time slot is available for a doctor
    """
    from datetime import timezone as tz
    
    # Ensure scheduled_datetime is timezone-aware
    if scheduled_datetime.tzinfo is None:
        scheduled_datetime = scheduled_datetime.replace(tzinfo=tz.utc)
    
    start_time = scheduled_datetime
    end_time = scheduled_datetime + datetime.timedelta(minutes=duration_minutes)
    
    # Helper function to make datetime timezone-aware
    def make_aware(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz.utc)
        return dt
    
    # Check for overlapping appointments
    query = select(Appointment).filter(
        and_(
            Appointment.doctor_id == doctor_id,
            Appointment.clinic_id == clinic_id,
            Appointment.status.in_([
                AppointmentStatus.SCHEDULED,
                AppointmentStatus.CHECKED_IN,
                AppointmentStatus.IN_CONSULTATION
            ])
        )
    )
    
    if exclude_appointment_id:
        query = query.filter(Appointment.id != exclude_appointment_id)
    
    result = await db.execute(query)
    appointments = result.scalars().all()
    
    # Check for overlap manually to handle timezone-aware comparisons
    for apt in appointments:
        apt_start = make_aware(apt.scheduled_datetime)
        if apt_start:
            apt_end = apt_start + datetime.timedelta(minutes=apt.duration_minutes or 30)
            
            # Check for overlap: appointment starts before this slot ends AND ends after this slot starts
            if not (end_time <= apt_start or start_time >= apt_end):
                return False
    
    return True


@router.get("", response_model=List[AppointmentListResponse])
async def list_appointments(
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
    start_date: Optional[datetime.date] = Query(None),
    end_date: Optional[datetime.date] = Query(None),
    doctor_id: Optional[int] = Query(None),
    patient_id: Optional[int] = Query(None),
    status: Optional[AppointmentStatus] = Query(None),
):
    """
    List appointments with optional filters
    """
    query = select(Appointment, Patient, User).join(
        Patient, Appointment.patient_id == Patient.id
    ).join(
        User, Appointment.doctor_id == User.id
    ).filter(
        Appointment.clinic_id == current_user.clinic_id
    )
    
    # Apply filters
    if start_date:
        start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
        query = query.filter(Appointment.scheduled_datetime >= start_datetime)
    
    if end_date:
        end_datetime = datetime.datetime.combine(end_date, datetime.time.max)
        query = query.filter(Appointment.scheduled_datetime <= end_datetime)
    
    if doctor_id:
        query = query.filter(Appointment.doctor_id == doctor_id)
    
    if patient_id:
        query = query.filter(Appointment.patient_id == patient_id)
    
    if status:
        query = query.filter(Appointment.status == status)
    
    query = query.order_by(Appointment.scheduled_datetime)
    
    result = await db.execute(query)
    appointments_data = result.all()
    
    # Build response with patient and doctor names
    response = []
    for appointment, patient, doctor in appointments_data:
        response.append(AppointmentListResponse(
            id=appointment.id,
            scheduled_datetime=appointment.scheduled_datetime,
            status=appointment.status,
            appointment_type=appointment.appointment_type,
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            patient_name=f"{patient.first_name} {patient.last_name}",
            doctor_name=f"{doctor.first_name} {doctor.last_name}",
        ))
    
    return response


@router.get("/doctor/my-appointments", response_model=List[AppointmentListResponse])
async def get_my_doctor_appointments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    start_date: Optional[datetime.date] = Query(None),
    end_date: Optional[datetime.date] = Query(None),
    status: Optional[AppointmentStatus] = Query(None),
):
    """
    Get appointments for the current doctor - automatically filters by doctor_id
    This endpoint is accessible to doctors only
    """
    # Only allow doctors to access this endpoint
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for doctors"
        )
    
    query = select(Appointment, Patient, User).join(
        Patient, Appointment.patient_id == Patient.id
    ).join(
        User, Appointment.doctor_id == User.id
    ).filter(
        and_(
            Appointment.doctor_id == current_user.id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    
    # Apply filters
    if start_date:
        start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
        query = query.filter(Appointment.scheduled_datetime >= start_datetime)
    
    if end_date:
        end_datetime = datetime.datetime.combine(end_date, datetime.time.max)
        query = query.filter(Appointment.scheduled_datetime <= end_datetime)
    
    if status:
        query = query.filter(Appointment.status == status)
    
    query = query.order_by(Appointment.scheduled_datetime)
    
    result = await db.execute(query)
    appointments_data = result.all()
    
    # Build response with patient and doctor names
    response = []
    for appointment, patient, doctor in appointments_data:
        response.append(AppointmentListResponse(
            id=appointment.id,
            scheduled_datetime=appointment.scheduled_datetime,
            status=appointment.status,
            appointment_type=appointment.appointment_type,
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            patient_name=f"{patient.first_name} {patient.last_name}".strip() or patient.email or "Paciente",
            doctor_name=f"{doctor.first_name} {doctor.last_name}".strip() or doctor.username or "Médico",
        ))
    
    return response


@router.get("/patient-appointments", response_model=List[AppointmentListResponse])
async def get_patient_appointments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    status: Optional[AppointmentStatus] = Query(None),
):
    """
    Get appointments for the current user (patient) - NEW ENDPOINT
    This endpoint is accessible to all authenticated users, with role checking inside.
    """
    # Only allow patients to access this endpoint
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for patients"
        )
    
    # Find the patient record that corresponds to the current user
    # Since there's no direct user_id in Patient, we'll match by email
    patient_query = select(Patient).filter(
        and_(
            Patient.email == current_user.email,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    
    if not patient:
        # If no patient record found, return empty list
        return []
    
    query = select(Appointment, Patient, User).join(
        Patient, Appointment.patient_id == Patient.id
    ).join(
        User, Appointment.doctor_id == User.id
    ).filter(
        and_(
            Appointment.patient_id == patient.id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    
    # Apply status filter if provided
    if status:
        query = query.filter(Appointment.status == status)
    
    result = await db.execute(query)
    appointments = result.all()
    
    appointment_list = []
    for appointment, patient, doctor in appointments:
        appointment_list.append(AppointmentListResponse(
            id=appointment.id,
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            scheduled_datetime=appointment.scheduled_datetime,
            duration_minutes=appointment.duration_minutes,
            status=appointment.status,
            appointment_type=appointment.appointment_type,
            reason=appointment.reason,
            notes=appointment.notes,
            patient_name=patient.full_name,
            doctor_name=doctor.full_name,
            created_at=appointment.created_at,
            updated_at=appointment.updated_at
        ))
    
    return appointment_list


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_patient_appointment(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Allow a patient to cancel their own appointment.
    """
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only patients can cancel via this endpoint")

    # Map user to patient by email and clinic
    patient_result = await db.execute(select(Patient).filter(and_(Patient.email == current_user.email, Patient.clinic_id == current_user.clinic_id)))
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    appt_result = await db.execute(select(Appointment).filter(and_(Appointment.id == appointment_id, Appointment.patient_id == patient.id, Appointment.clinic_id == current_user.clinic_id)))
    appt = appt_result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    appt.status = AppointmentStatus.CANCELLED
    await db.commit()
    await db.refresh(appt)

    # Build response with patient and doctor names
    doc = await db.get(User, appt.doctor_id)
    pat = await db.get(Patient, appt.patient_id)
    return AppointmentResponse(
        id=appt.id,
        patient_id=appt.patient_id,
        doctor_id=appt.doctor_id,
        scheduled_datetime=appt.scheduled_datetime,
        duration_minutes=appt.duration_minutes,
        status=appt.status,
        appointment_type=appt.appointment_type,
        reason=appt.reason,
        notes=appt.notes,
        patient_name=pat.full_name if pat else None,
        doctor_name=f"{doc.first_name} {doc.last_name}" if doc else None,
        created_at=appt.created_at,
        updated_at=appt.updated_at,
    )


class ReschedulePayload(AppointmentUpdate):
    pass


@router.post("/patient/book", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def book_patient_appointment(
    appointment_in: AppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Allow a patient to book a new appointment
    """
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for patients"
        )
    
    # Map user to patient by email and clinic
    patient_result = await db.execute(
        select(Patient).filter(
            and_(
                Patient.email == current_user.email,
                Patient.clinic_id == current_user.clinic_id
            )
        )
    )
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Ensure appointment is for the current patient
    if appointment_in.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create appointment for a different patient"
        )
    
    # Ensure appointment is for the current clinic
    if appointment_in.clinic_id != current_user.clinic_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create appointment for a different clinic"
        )
    
    # Validate doctor exists and has doctor role
    doctor_query = select(User).filter(
        and_(
            User.id == appointment_in.doctor_id,
            User.clinic_id == current_user.clinic_id,
            User.role == UserRole.DOCTOR
        )
    )
    doctor_result = await db.execute(doctor_query)
    doctor = doctor_result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Check slot availability
    is_available = await check_slot_availability(
        db,
        appointment_in.doctor_id,
        appointment_in.scheduled_datetime,
        current_user.clinic_id
    )
    
    if not is_available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This time slot is not available for the selected doctor"
        )
    
    # Create appointment
    appointment_data = appointment_in.model_dump()
    # If no explicit appointment_type was provided, default to doctor's consultation_room (if any)
    if not appointment_data.get("appointment_type") and getattr(doctor, "consultation_room", None):
        appointment_data["appointment_type"] = doctor.consultation_room

    db_appointment = Appointment(**appointment_data)
    db.add(db_appointment)
    await db.commit()
    await db.refresh(db_appointment)
    
    # Build response with patient and doctor names
    response = AppointmentResponse.model_validate(db_appointment)
    response.patient_name = patient.full_name
    response.doctor_name = doctor.full_name
    
    # Broadcast event
    await appointment_realtime_manager.broadcast(
        current_user.clinic_id,
        {
            "type": "appointment_created",
            "appointment_id": db_appointment.id,
            "status": str(db_appointment.status),
        },
    )
    
    return response


@router.get("/doctor/{doctor_id}/availability")
async def get_doctor_availability(
    doctor_id: int,
    date: datetime.date = Query(..., description="Date to check availability"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get available time slots for a doctor on a specific date
    """
    from datetime import timezone as tz
    
    # Validate doctor exists and belongs to same clinic
    doctor_query = select(User).filter(
        and_(
            User.id == doctor_id,
            User.clinic_id == current_user.clinic_id,
            User.role == UserRole.DOCTOR
        )
    )
    doctor_result = await db.execute(doctor_query)
    doctor = doctor_result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Get all appointments for this doctor on this date
    # Use timezone-aware datetimes
    start_datetime = datetime.datetime.combine(date, datetime.time.min).replace(tzinfo=tz.utc)
    end_datetime = datetime.datetime.combine(date, datetime.time.max).replace(tzinfo=tz.utc)
    
    appointments_query = select(Appointment).filter(
        and_(
            Appointment.doctor_id == doctor_id,
            Appointment.clinic_id == current_user.clinic_id,
            Appointment.scheduled_datetime >= start_datetime,
            Appointment.scheduled_datetime <= end_datetime,
            Appointment.status.in_([
                AppointmentStatus.SCHEDULED,
                AppointmentStatus.CHECKED_IN,
                AppointmentStatus.IN_CONSULTATION
            ])
        )
    )
    appointments_result = await db.execute(appointments_query)
    appointments = appointments_result.scalars().all()
    
    # Helper function to make datetime timezone-aware
    def make_aware(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz.utc)
        return dt
    
    # Generate time slots (8:00 to 18:00, 30-minute intervals)
    available_slots = []
    start_hour = 8
    end_hour = 18
    
    for hour in range(start_hour, end_hour):
        for minute in [0, 30]:
            slot_time = datetime.datetime.combine(date, datetime.time(hour, minute)).replace(tzinfo=tz.utc)
            slot_end = slot_time + datetime.timedelta(minutes=30)
            
            # Check if this slot conflicts with any appointment
            is_available = True
            for apt in appointments:
                apt_start = make_aware(apt.scheduled_datetime)
                if apt_start:
                    apt_end = apt_start + datetime.timedelta(minutes=apt.duration_minutes or 30)
                    
                    # Check for overlap
                    if not (slot_end <= apt_start or slot_time >= apt_end):
                        is_available = False
                        break
            
            available_slots.append({
                "time": slot_time.strftime("%H:%M"),
                "datetime": slot_time.isoformat(),
                "available": is_available
            })
    
    return {
        "doctor_id": doctor_id,
        "doctor_name": f"{doctor.first_name} {doctor.last_name}",
        "date": date.isoformat(),
        "slots": available_slots
    }


@router.get("/today-patients", response_model=list[TodayPatientResponse])
async def get_today_patients(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Return patients with appointments today for the current clinic.

    - Doctors see only their own appointments.
    - Secretaries/Admins see all doctors' appointments.
    """
    from datetime import timezone as tz

    now = datetime.datetime.now(tz.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + datetime.timedelta(days=1)

    query = select(Appointment, Patient, User).join(
        Patient, Appointment.patient_id == Patient.id
    ).join(
        User, Appointment.doctor_id == User.id
    ).filter(
        and_(
            Appointment.clinic_id == current_user.clinic_id,
            Appointment.scheduled_datetime >= today_start,
            Appointment.scheduled_datetime < today_end,
        )
    )

    # If doctor, restrict to their own appointments
    if current_user.role == UserRole.DOCTOR:
        query = query.filter(Appointment.doctor_id == current_user.id)

    result = await db.execute(query.order_by(Appointment.scheduled_datetime))
    rows = result.all()

    # Deduplicate by (appointment_id) – we want one entry per appointment
    out: list[TodayPatientResponse] = []
    for appt, patient, doctor in rows:
        patient_name = f"{patient.first_name or ''} {patient.last_name or ''}".strip() or patient.email or "Paciente"
        doctor_name = f"{doctor.first_name or ''} {doctor.last_name or ''}".strip() or doctor.username or "Médico"
        out.append(
            TodayPatientResponse(
                appointment_id=appt.id,
                patient_id=patient.id,
                patient_name=patient_name,
                doctor_id=doctor.id,
                doctor_name=doctor_name,
                scheduled_datetime=appt.scheduled_datetime,
            )
        )

    return out


@router.post("/{appointment_id}/reschedule", response_model=AppointmentResponse)
async def reschedule_patient_appointment(
    appointment_id: int,
    payload: ReschedulePayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Allow a patient to reschedule their own appointment (date/time and optional reason/notes).
    Checks slot availability for the same doctor.
    """
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only patients can reschedule via this endpoint")

    patient_result = await db.execute(select(Patient).filter(and_(Patient.email == current_user.email, Patient.clinic_id == current_user.clinic_id)))
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    appt_result = await db.execute(select(Appointment).filter(and_(Appointment.id == appointment_id, Appointment.patient_id == patient.id, Appointment.clinic_id == current_user.clinic_id)))
    appt = appt_result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Only reschedule datetime (and optional reason/notes)
    if payload.scheduled_datetime:
        available = await check_slot_availability(db, appt.doctor_id, payload.scheduled_datetime, current_user.clinic_id, exclude_appointment_id=appt.id, duration_minutes=payload.duration_minutes or appt.duration_minutes)
        if not available:
            raise HTTPException(status_code=400, detail="Selected time slot is not available")
        appt.scheduled_datetime = payload.scheduled_datetime
    if payload.duration_minutes:
        appt.duration_minutes = payload.duration_minutes
    if payload.reason is not None:
        appt.reason = payload.reason
    if payload.notes is not None:
        appt.notes = payload.notes

    await db.commit()
    await db.refresh(appt)

    doc = await db.get(User, appt.doctor_id)
    pat = await db.get(Patient, appt.patient_id)
    return AppointmentResponse(
        id=appt.id,
        patient_id=appt.patient_id,
        doctor_id=appt.doctor_id,
        scheduled_datetime=appt.scheduled_datetime,
        duration_minutes=appt.duration_minutes,
        status=appt.status,
        appointment_type=appt.appointment_type,
        reason=appt.reason,
        notes=appt.notes,
        patient_name=pat.full_name if pat else None,
        doctor_name=f"{doc.first_name} {doc.last_name}" if doc else None,
        created_at=appt.created_at,
        updated_at=appt.updated_at,
    )


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get a specific appointment by ID
    """
    query = select(Appointment, Patient, User).join(
        Patient, Appointment.patient_id == Patient.id
    ).join(
        User, Appointment.doctor_id == User.id
    ).filter(
        and_(
            Appointment.id == appointment_id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    
    result = await db.execute(query)
    appointment_data = result.first()
    
    if not appointment_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    appointment, patient, doctor = appointment_data
    
    # Create response with additional fields
    response = AppointmentResponse.model_validate(appointment)
    response.patient_name = f"{patient.first_name} {patient.last_name}"
    response.doctor_name = f"{doctor.first_name} {doctor.last_name}"
    
    return response


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    appointment_in: AppointmentCreate,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new appointment
    """
    # Ensure the appointment is created for the current user's clinic
    if appointment_in.clinic_id != current_user.clinic_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create appointment for a different clinic"
        )
    
    # Validate patient exists
    patient_query = select(Patient).filter(
        and_(
            Patient.id == appointment_in.patient_id,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    # Validate doctor exists and has doctor role
    doctor_query = select(User).filter(
        and_(
            User.id == appointment_in.doctor_id,
            User.clinic_id == current_user.clinic_id,
            User.role == UserRole.DOCTOR
        )
    )
    doctor_result = await db.execute(doctor_query)
    doctor = doctor_result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Check slot availability
    is_available = await check_slot_availability(
        db,
        appointment_in.doctor_id,
        appointment_in.scheduled_datetime,
        current_user.clinic_id
    )
    
    if not is_available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This time slot is not available for the selected doctor"
        )
    
    # Create appointment
    appointment_data = appointment_in.model_dump()
    # If no explicit appointment_type was provided, default to doctor's consultation_room (if any)
    if not appointment_data.get("appointment_type") and getattr(doctor, "consultation_room", None):
        appointment_data["appointment_type"] = doctor.consultation_room

    db_appointment = Appointment(**appointment_data)
    db.add(db_appointment)
    await db.commit()
    await db.refresh(db_appointment)
    
    # Add patient and doctor names to response
    response = AppointmentResponse.model_validate(db_appointment)
    response.patient_name = patient.full_name
    response.doctor_name = doctor.full_name
    
    # Broadcast event
    await appointment_realtime_manager.broadcast(
        current_user.clinic_id,
        {
            "type": "appointment_created",
            "appointment_id": db_appointment.id,
            "status": str(db_appointment.status),
        },
    )

    return response


@router.put("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: int,
    appointment_in: AppointmentUpdate,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update an appointment
    """
    # Get existing appointment
    query = select(Appointment).filter(
        and_(
            Appointment.id == appointment_id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_appointment = result.scalar_one_or_none()
    
    if not db_appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # If rescheduling, check slot availability
    if appointment_in.scheduled_datetime:
        doctor_id = appointment_in.doctor_id or db_appointment.doctor_id
        is_available = await check_slot_availability(
            db,
            doctor_id,
            appointment_in.scheduled_datetime,
            current_user.clinic_id,
            exclude_appointment_id=appointment_id
        )
        
        if not is_available:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This time slot is not available for the selected doctor"
            )
    
    # Update appointment fields
    update_data = appointment_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_appointment, field, value)
    
    await db.commit()
    await db.refresh(db_appointment)
    
    # Get patient and doctor names
    patient_query = select(Patient).filter(Patient.id == db_appointment.patient_id)
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one()
    
    doctor_query = select(User).filter(User.id == db_appointment.doctor_id)
    doctor_result = await db.execute(doctor_query)
    doctor = doctor_result.scalar_one()
    
    response = AppointmentResponse.model_validate(db_appointment)
    response.patient_name = patient.full_name
    response.doctor_name = doctor.full_name
    
    # Broadcast event
    await appointment_realtime_manager.broadcast(
        current_user.clinic_id,
        {
            "type": "appointment_updated",
            "appointment_id": db_appointment.id,
            "status": str(db_appointment.status),
        },
    )

    return response


@router.get("/doctor/queue", response_model=List[dict])
async def get_doctor_queue(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get the queue of patients for the current doctor
    Returns patients with status CHECKED_IN (waiting) and IN_CONSULTATION (in consultation)
    """
    from datetime import timezone as tz
    
    # Only allow doctors to access this endpoint
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for doctors"
        )
    
    now = datetime.datetime.now(tz.utc)
    
    # Get all appointments for today with status CHECKED_IN or IN_CONSULTATION
    queue_query = select(Appointment, Patient).join(
        Patient, Appointment.patient_id == Patient.id
    ).filter(
        and_(
            Appointment.doctor_id == current_user.id,
            Appointment.clinic_id == current_user.clinic_id,
            Appointment.status.in_([
                AppointmentStatus.CHECKED_IN,
                AppointmentStatus.IN_CONSULTATION
            ]),
            # Only today's appointments
            Appointment.scheduled_datetime >= now.replace(hour=0, minute=0, second=0, microsecond=0),
            Appointment.scheduled_datetime < (now.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1))
        )
    ).order_by(
        # IN_CONSULTATION first, then by scheduled_datetime
        Appointment.status.desc(),
        Appointment.scheduled_datetime
    )
    
    result = await db.execute(queue_query)
    appointments_data = result.all()
    
    queue_items = []
    for appointment, patient in appointments_data:
        # Calculate wait time
        wait_time_minutes = 0
        wait_time_str = "0 min"
        
        if appointment.status == AppointmentStatus.CHECKED_IN:
            # Calculate from checked_in_at or scheduled_datetime
            if appointment.checked_in_at:
                wait_start = appointment.checked_in_at
            else:
                wait_start = appointment.scheduled_datetime
            
            if wait_start:
                # Make timezone-aware if needed
                if wait_start.tzinfo is None:
                    wait_start = wait_start.replace(tzinfo=tz.utc)
                
                wait_delta = now - wait_start
                wait_time_minutes = int(wait_delta.total_seconds() / 60)
                wait_time_str = f"{wait_time_minutes} min"
        elif appointment.status == AppointmentStatus.IN_CONSULTATION:
            # Calculate from started_at
            if appointment.started_at:
                wait_start = appointment.started_at
                if wait_start.tzinfo is None:
                    wait_start = wait_start.replace(tzinfo=tz.utc)
                
                wait_delta = now - wait_start
                wait_time_minutes = int(wait_delta.total_seconds() / 60)
                wait_time_str = f"{wait_time_minutes} min"
        
        # Get patient name
        patient_name = f"{patient.first_name or ''} {patient.last_name or ''}".strip()
        if not patient_name:
            patient_name = patient.email or "Paciente"
        
        # Format appointment time
        apt_datetime = appointment.scheduled_datetime
        if apt_datetime.tzinfo is None:
            apt_datetime = apt_datetime.replace(tzinfo=tz.utc)
        appointment_time = apt_datetime.strftime("%H:%M")
        
        queue_items.append({
            "id": appointment.id,
            "patient_id": patient.id,
            "patient_name": patient_name,
            "appointment_time": appointment_time,
            "scheduled_datetime": appointment.scheduled_datetime.isoformat(),
            "wait_time": wait_time_str,
            "wait_time_minutes": wait_time_minutes,
            "status": appointment.status.value if hasattr(appointment.status, 'value') else str(appointment.status),
            "appointment_type": appointment.appointment_type,
            "checked_in_at": appointment.checked_in_at.isoformat() if appointment.checked_in_at else None,
            "started_at": appointment.started_at.isoformat() if appointment.started_at else None,
        })
    
    return queue_items


@router.patch("/{appointment_id}/status", response_model=AppointmentResponse)
async def update_appointment_status(
    appointment_id: int,
    status_update: AppointmentStatusUpdate,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update appointment status (check-in, start consultation, complete, cancel)
    """
    from datetime import timezone as tz
    
    query = select(Appointment).filter(
        and_(
            Appointment.id == appointment_id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_appointment = result.scalar_one_or_none()
    
    if not db_appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # Update status and timestamps
    old_status = db_appointment.status
    db_appointment.status = status_update.status
    now = datetime.datetime.now(tz.utc)
    
    # Update timestamps based on status
    if status_update.status == AppointmentStatus.CHECKED_IN:
        if not db_appointment.checked_in_at:
            db_appointment.checked_in_at = now
    elif status_update.status == AppointmentStatus.IN_CONSULTATION:
        if not db_appointment.started_at:
            db_appointment.started_at = now
    elif status_update.status == AppointmentStatus.COMPLETED:
        if not db_appointment.completed_at:
            db_appointment.completed_at = now
    
    await db.commit()
    await db.refresh(db_appointment)
    
    # Get patient and doctor names
    patient_query = select(Patient).filter(Patient.id == db_appointment.patient_id)
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one()
    
    doctor_query = select(User).filter(User.id == db_appointment.doctor_id)
    doctor_result = await db.execute(doctor_query)
    doctor = doctor_result.scalar_one()
    
    response = AppointmentResponse.model_validate(db_appointment)
    response.patient_name = patient.full_name
    response.doctor_name = doctor.full_name
    
    # Broadcast status change
    await appointment_realtime_manager.broadcast(
        current_user.clinic_id,
        {
            "type": "appointment_status",
            "appointment_id": db_appointment.id,
            "status": str(db_appointment.status),
        },
    )

    return response


@router.websocket("/ws/appointments")
async def appointments_ws(websocket: WebSocket):
    """WebSocket channel for appointment updates, tenant-isolated via header token parsing upstream middleware.
    Requires AuthenticationMiddleware to set request.state.user_id and ideally clinic_id in token.
    We parse Authorization header from websocket headers manually and fetch clinic_id from token using existing logic.
    """
    try:
        # Extract Authorization header or token query param
        auth_header = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
        clinic_id: int | None = None
        token_value: str | None = None
        if auth_header and auth_header.startswith("Bearer "):
            token_value = auth_header.split(" ")[1]
        if not token_value:
            try:
                # Parse query string from URL
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(str(websocket.url))
                query_params = parse_qs(parsed_url.query)
                token_value = query_params.get("token", [None])[0]
            except Exception:
                token_value = None
        if token_value:
            try:
                from app.core.auth import verify_token
                payload = verify_token(token_value)
                clinic_id = payload.get("clinic_id")
            except Exception as e:
                print(f"Token verification failed: {e}")
                clinic_id = None
        if clinic_id is None:
            # Reject if tenant unknown
            await websocket.close(code=4401, reason="Invalid or missing token")
            return

        await appointment_realtime_manager.connect(clinic_id, websocket)
        try:
            while True:
                # Keep the socket alive; we don't expect inbound messages right now
                await websocket.receive_text()
        except WebSocketDisconnect:
            await appointment_realtime_manager.disconnect(clinic_id, websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.close(code=4400, reason="Internal error")
        except:
            pass


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete an appointment (admin only)
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete appointments"
        )
    
    query = select(Appointment).filter(
        and_(
            Appointment.id == appointment_id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_appointment = result.scalar_one_or_none()
    
    if not db_appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    await db.delete(db_appointment)
    await db.commit()
    
    return None


@router.post("/{appointment_id}/consultation-token")
async def generate_consultation_token(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate a unique room token for video consultation
    """
    # Verify appointment exists and user has access
    appointment_query = select(Appointment).filter(
        and_(
            Appointment.id == appointment_id,
            or_(
                Appointment.patient_id == current_user.id,  # Patient can access their own appointments
                Appointment.doctor_id == current_user.id,   # Doctor can access their appointments
                current_user.role == UserRole.ADMIN,        # Admin can access all
                current_user.role == UserRole.SECRETARY     # Secretary can access all
            )
        )
    )
    appointment_result = await db.execute(appointment_query)
    appointment = appointment_result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found or access denied"
        )
    
    # Check if appointment is scheduled for today or in the future
    now = datetime.datetime.now(datetime.timezone.utc)
    if appointment.scheduled_datetime < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate token for past appointments"
        )
    
    # Generate a unique room token
    import secrets
    room_token = f"room_{appointment_id}_{secrets.token_urlsafe(16)}"
    
    return {
        "token": room_token,
        "appointment_id": appointment_id,
        "expires_at": appointment.scheduled_datetime.isoformat(),
        "room_name": f"consultation-{appointment_id}"
    }


@router.get("/available-slots")
async def get_available_slots(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    doctor_id: int = Query(..., description="Doctor ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get available time slots for a specific doctor on a specific date
    """
    try:
        # Parse date
        appointment_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD"
        )
    
    # Verify doctor exists
    doctor_query = select(User).filter(
        and_(
            User.id == doctor_id,
            User.role == UserRole.DOCTOR,
            User.clinic_id == current_user.clinic_id
        )
    )
    doctor_result = await db.execute(doctor_query)
    doctor = doctor_result.scalar_one_or_none()
    
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Generate time slots (9 AM to 5 PM, 30-minute intervals)
    time_slots = []
    start_time = datetime.time(9, 0)  # 9:00 AM
    end_time = datetime.time(17, 0)   # 5:00 PM
    
    current_time = start_time
    while current_time < end_time:
        slot_datetime = datetime.datetime.combine(appointment_date, current_time)
        slot_datetime = slot_datetime.replace(tzinfo=datetime.timezone.utc)
        
        # Check if slot is available
        is_available = await check_slot_availability(
            db, doctor_id, slot_datetime, 30
        )
        
        time_slots.append({
            "time": current_time.strftime("%H:%M"),
            "available": is_available,
            "datetime": slot_datetime.isoformat()
        })
        
        # Move to next slot (30 minutes)
        current_time = datetime.time(
            current_time.hour,
            current_time.minute + 30
        )
    
    return time_slots


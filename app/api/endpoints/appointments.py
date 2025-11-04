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
from database import get_async_session
from app.services.realtime import appointment_realtime_manager

router = APIRouter(prefix="/appointments", tags=["Appointments"])

# Role checker for staff (admin, secretary, doctor)
require_staff = RoleChecker([UserRole.ADMIN, UserRole.SECRETARY, UserRole.DOCTOR])


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
    start_time = scheduled_datetime
    end_time = scheduled_datetime + datetime.timedelta(minutes=duration_minutes)
    
    # Check for overlapping appointments
    query = select(Appointment).filter(
        and_(
            Appointment.doctor_id == doctor_id,
            Appointment.clinic_id == clinic_id,
            Appointment.status.in_([
                AppointmentStatus.SCHEDULED,
                AppointmentStatus.CHECKED_IN,
                AppointmentStatus.IN_CONSULTATION
            ]),
            # Check for overlap: appointment starts before this slot ends AND ends after this slot starts
            Appointment.scheduled_datetime < end_time,
            Appointment.scheduled_datetime >= start_time - datetime.timedelta(minutes=duration_minutes)
        )
    )
    
    if exclude_appointment_id:
        query = query.filter(Appointment.id != exclude_appointment_id)
    
    result = await db.execute(query)
    overlapping = result.scalars().first()
    
    return overlapping is None


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
    db_appointment = Appointment(**appointment_in.model_dump())
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
    
    db_appointment.status = status_update.status
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


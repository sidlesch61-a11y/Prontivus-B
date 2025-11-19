"""
Patient Dashboard API Endpoints
Provides aggregated data for patient dashboard
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from sqlalchemy.orm import joinedload, selectinload

from app.core.auth import get_current_user
from app.models import User, Patient, Appointment, AppointmentStatus, UserRole
from app.models.clinical import ClinicalRecord, Prescription, ExamRequest
from app.models.financial import Invoice, Payment, InvoiceStatus, PaymentStatus
from app.models.message import MessageThread, Message, MessageStatus
from database import get_async_session
from pydantic import BaseModel

router = APIRouter(prefix="/patient", tags=["Patient Dashboard"])


# ==================== Response Models ====================

class PatientDashboardStats(BaseModel):
    """Patient dashboard statistics"""
    upcoming_appointments_count: int
    active_prescriptions_count: int
    pending_exam_results_count: int
    unread_messages_count: int
    pending_payments_count: int
    total_payments_amount: float
    last_appointment_date: Optional[datetime]
    active_conditions_count: int
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class UpcomingAppointmentResponse(BaseModel):
    """Upcoming appointment response"""
    id: int
    scheduled_datetime: datetime
    doctor_name: str
    doctor_specialty: Optional[str]
    appointment_type: Optional[str]
    status: str
    location: Optional[str]
    is_virtual: bool
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class RecentActivityResponse(BaseModel):
    """Recent activity response"""
    id: int
    type: str  # "appointment", "prescription", "exam_result", "message", "payment"
    title: str
    description: str
    date: datetime
    icon: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class HealthSummaryResponse(BaseModel):
    """Health summary response"""
    active_prescriptions_count: int
    active_conditions_count: int
    last_measurement_date: Optional[datetime]
    pending_exams_count: int
    completed_exams_count: int
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class PatientDashboardResponse(BaseModel):
    """Complete patient dashboard response"""
    stats: PatientDashboardStats
    upcoming_appointment: Optional[UpcomingAppointmentResponse]
    recent_activities: List[RecentActivityResponse]
    health_summary: HealthSummaryResponse


# ==================== Helper Functions ====================

def get_user_full_name(user: User) -> str:
    """Safely get user's full name"""
    if hasattr(user, 'full_name') and callable(getattr(user, 'full_name', None)):
        try:
            return user.full_name
        except:
            pass
    if user.first_name or user.last_name:
        return f"{user.first_name or ''} {user.last_name or ''}".strip()
    return user.username or "Usuário"


async def get_patient_from_user(
    current_user: User,
    db: AsyncSession
) -> Optional[Patient]:
    """Get Patient record from User by email"""
    if current_user.role != UserRole.PATIENT:
        return None
    
    query = select(Patient).filter(
        and_(
            Patient.email == current_user.email,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


# ==================== Dashboard Endpoint ====================

@router.get("/dashboard", response_model=PatientDashboardResponse)
async def get_patient_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get comprehensive patient dashboard data
    
    Returns:
    - Statistics (counts of appointments, prescriptions, messages, etc.)
    - Upcoming appointment
    - Recent activities
    - Health summary
    """
    try:
        # Verify user is a patient
        if current_user.role != UserRole.PATIENT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available for patients"
            )
        
        # Get patient record
        patient = await get_patient_from_user(current_user, db)
        if not patient:
            # Return empty dashboard if patient record not found
            return PatientDashboardResponse(
                stats=PatientDashboardStats(
                    upcoming_appointments_count=0,
                    active_prescriptions_count=0,
                    pending_exam_results_count=0,
                    unread_messages_count=0,
                    pending_payments_count=0,
                    total_payments_amount=0.0,
                    last_appointment_date=None,
                    active_conditions_count=0
                ),
                upcoming_appointment=None,
                recent_activities=[],
                health_summary=HealthSummaryResponse(
                    active_prescriptions_count=0,
                    active_conditions_count=0,
                    last_measurement_date=None,
                    pending_exams_count=0,
                    completed_exams_count=0
                )
            )
        
        # Use timezone-aware datetime to avoid comparison errors
        now = datetime.now(timezone.utc)
        now_date = now.date()
        
        # ==================== Get Appointments ====================
        appointments_query = select(Appointment, User).join(
            User, Appointment.doctor_id == User.id
        ).filter(
            and_(
                Appointment.patient_id == patient.id,
                Appointment.clinic_id == current_user.clinic_id
            )
        )
        
        appointments_result = await db.execute(appointments_query)
        appointments_data = appointments_result.all()
        
        # Helper function to make datetime timezone-aware if needed
        def make_aware(dt):
            if dt is None:
                return None
            if dt.tzinfo is None:
                # Assume UTC if naive
                return dt.replace(tzinfo=timezone.utc)
            return dt
        
        # Upcoming appointments
        upcoming_appointments = []
        for apt, doc in appointments_data:
            apt_datetime = make_aware(apt.scheduled_datetime)
            if apt_datetime and apt_datetime >= now and apt.status in [
                AppointmentStatus.SCHEDULED,
                AppointmentStatus.CHECKED_IN
            ]:
                upcoming_appointments.append((apt, doc))
        upcoming_appointments.sort(key=lambda x: make_aware(x[0].scheduled_datetime) or datetime.min.replace(tzinfo=timezone.utc))
        
        # Last appointment
        past_appointments = []
        for apt, doc in appointments_data:
            apt_datetime = make_aware(apt.scheduled_datetime)
            if apt_datetime and apt_datetime < now:
                past_appointments.append((apt, doc))
        past_appointments.sort(key=lambda x: make_aware(x[0].scheduled_datetime) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        last_appointment_date = make_aware(past_appointments[0][0].scheduled_datetime) if past_appointments else None
        
        # Next upcoming appointment
        upcoming_appointment = None
        if upcoming_appointments:
            apt, doc = upcoming_appointments[0]
            # Ensure scheduled_datetime is timezone-aware
            apt_datetime = make_aware(apt.scheduled_datetime)
            # Safely get doctor name
            doctor_name = get_user_full_name(doc)
            
            upcoming_appointment = UpcomingAppointmentResponse(
                id=apt.id,
                scheduled_datetime=apt_datetime or now,
                doctor_name=doctor_name,
                doctor_specialty=apt.appointment_type or "",
                appointment_type=apt.appointment_type or "",
                status=apt.status.value if hasattr(apt.status, 'value') else str(apt.status),
                location=None,  # TODO: Add location field if available
                is_virtual=apt.appointment_type and "virtual" in apt.appointment_type.lower() if apt.appointment_type else False
            )
        
        # ==================== Get Prescriptions ====================
        # Get all clinical records for this patient's appointments
        appointment_ids = [apt.id for apt, _ in appointments_data]
        
        active_prescriptions_count = 0
        if appointment_ids:
            prescriptions_query = select(Prescription).join(
                ClinicalRecord, Prescription.clinical_record_id == ClinicalRecord.id
            ).filter(
                and_(
                    ClinicalRecord.appointment_id.in_(appointment_ids),
                    Prescription.is_active == True
                )
            )
            prescriptions_result = await db.execute(prescriptions_query)
            active_prescriptions = prescriptions_result.scalars().all()
            active_prescriptions_count = len(active_prescriptions)
        
        # ==================== Get Exam Requests ====================
        pending_exam_results_count = 0
        completed_exams_count = 0
        if appointment_ids:
            exam_requests_query = select(ExamRequest).join(
                ClinicalRecord, ExamRequest.clinical_record_id == ClinicalRecord.id
            ).filter(
                ClinicalRecord.appointment_id.in_(appointment_ids)
            )
            exam_requests_result = await db.execute(exam_requests_query)
            exam_requests = exam_requests_result.scalars().all()
            
            for exam in exam_requests:
                if exam.completed and exam.completed_date:
                    completed_exams_count += 1
                else:
                    pending_exam_results_count += 1
        
        # ==================== Get Messages ====================
        messages_query = select(func.count(Message.id)).join(
            MessageThread, Message.thread_id == MessageThread.id
        ).filter(
            and_(
                MessageThread.patient_id == patient.id,
                MessageThread.clinic_id == current_user.clinic_id,
                Message.sender_type != "patient",
                Message.status != MessageStatus.READ.value
            )
        )
        messages_result = await db.execute(messages_query)
        unread_messages_count = messages_result.scalar() or 0
        
        # ==================== Get Payments ====================
        invoices_query = select(Invoice).filter(
            and_(
                Invoice.patient_id == patient.id,
                Invoice.clinic_id == current_user.clinic_id
            )
        )
        invoices_result = await db.execute(invoices_query)
        invoices = invoices_result.scalars().all()
        
        pending_payments_count = 0
        total_payments_amount = 0.0
        
        for invoice in invoices:
            if invoice.status == InvoiceStatus.PENDING:
                pending_payments_count += 1
            
            # Get payments for this invoice
            payments_query = select(Payment).filter(
                and_(
                    Payment.invoice_id == invoice.id,
                    Payment.status == PaymentStatus.COMPLETED
                )
            )
            payments_result = await db.execute(payments_query)
            payments = payments_result.scalars().all()
            
            for payment in payments:
                total_payments_amount += float(payment.amount)
        
        # ==================== Get Active Conditions ====================
        # Count diagnoses from clinical records
        active_conditions_count = 0
        if appointment_ids:
            clinical_records_query = select(ClinicalRecord).options(
                selectinload(ClinicalRecord.diagnoses)
            ).filter(
                ClinicalRecord.appointment_id.in_(appointment_ids)
            )
            clinical_records_result = await db.execute(clinical_records_query)
            clinical_records = clinical_records_result.scalars().all()
            
            for record in clinical_records:
                if record.diagnoses:
                    # Count all diagnoses as active conditions (model doesn't have is_active field)
                    active_conditions_count += len(record.diagnoses)
        
        # ==================== Build Recent Activities ====================
        recent_activities: List[RecentActivityResponse] = []
        
        # Add recent appointments
        for apt, doc in past_appointments[:5]:
            apt_datetime = make_aware(apt.scheduled_datetime)
            recent_activities.append(RecentActivityResponse(
                id=apt.id,
                type="appointment",
                title="Consulta Realizada" if apt.status == AppointmentStatus.COMPLETED else "Consulta",
                description=f"Dr(a). {get_user_full_name(doc)}",
                date=apt_datetime or now,
                icon="calendar"
            ))
        
        # Add recent prescriptions (last 5)
        if appointment_ids:
            recent_prescriptions_query = select(Prescription).join(
                ClinicalRecord, Prescription.clinical_record_id == ClinicalRecord.id
            ).join(
                Appointment, ClinicalRecord.appointment_id == Appointment.id
            ).join(
                User, Appointment.doctor_id == User.id
            ).filter(
                ClinicalRecord.appointment_id.in_(appointment_ids)
            ).order_by(Prescription.issued_date.desc()).limit(5)
            
            prescriptions_result = await db.execute(recent_prescriptions_query)
            recent_prescriptions = prescriptions_result.scalars().all()
            
            for presc in recent_prescriptions:
                # Get doctor name from appointment
                apt_query = select(Appointment, User).join(
                    User, Appointment.doctor_id == User.id
                ).join(
                    ClinicalRecord, Appointment.id == ClinicalRecord.appointment_id
                ).filter(
                    ClinicalRecord.id == presc.clinical_record_id
                )
                apt_result = await db.execute(apt_query)
                apt_data = apt_result.first()
                doctor_name = get_user_full_name(apt_data[1]) if apt_data and len(apt_data) > 1 else "Médico"
                
                # Create timezone-aware datetime from date
                presc_date = presc.issued_date
                if presc_date:
                    presc_datetime = datetime.combine(presc_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                else:
                    presc_datetime = now
                
                recent_activities.append(RecentActivityResponse(
                    id=presc.id,
                    type="prescription",
                    title=f"Prescrição: {presc.medication_name}",
                    description=f"Prescrito por {doctor_name}",
                    date=presc_datetime,
                    icon="pill"
                ))
        
        # Add recent exam results (last 5)
        if appointment_ids:
            recent_exams_query = select(ExamRequest).join(
                ClinicalRecord, ExamRequest.clinical_record_id == ClinicalRecord.id
            ).join(
                Appointment, ClinicalRecord.appointment_id == Appointment.id
            ).join(
                User, Appointment.doctor_id == User.id
            ).filter(
                and_(
                    ClinicalRecord.appointment_id.in_(appointment_ids),
                    ExamRequest.completed == True,
                    ExamRequest.completed_date.isnot(None)
                )
            ).order_by(ExamRequest.completed_date.desc()).limit(5)
            
            exams_result = await db.execute(recent_exams_query)
            recent_exams = exams_result.scalars().all()
            
            for exam in recent_exams:
                # Get doctor name
                apt_query = select(Appointment, User).join(
                    User, Appointment.doctor_id == User.id
                ).join(
                    ClinicalRecord, Appointment.id == ClinicalRecord.appointment_id
                ).filter(
                    ClinicalRecord.id == exam.clinical_record_id
                )
                apt_result = await db.execute(apt_query)
                apt_data = apt_result.first()
                doctor_name = get_user_full_name(apt_data[1]) if apt_data and len(apt_data) > 1 else "Médico"
                
                # Create timezone-aware datetime from completed_date
                exam_datetime = make_aware(exam.completed_date) if exam.completed_date else now
                
                recent_activities.append(RecentActivityResponse(
                    id=exam.id,
                    type="exam_result",
                    title=f"Resultado: {exam.exam_type}",
                    description=f"Resultado disponível - {doctor_name}",
                    date=exam_datetime or now,
                    icon="flask"
                ))
        
        # Sort activities by date (most recent first)
        recent_activities.sort(key=lambda x: x.date, reverse=True)
        recent_activities = recent_activities[:10]  # Limit to 10 most recent
        
        # ==================== Build Response ====================
        stats = PatientDashboardStats(
            upcoming_appointments_count=len(upcoming_appointments),
            active_prescriptions_count=active_prescriptions_count,
            pending_exam_results_count=pending_exam_results_count,
            unread_messages_count=unread_messages_count,
            pending_payments_count=pending_payments_count,
            total_payments_amount=total_payments_amount,
            last_appointment_date=last_appointment_date,
            active_conditions_count=active_conditions_count
        )
        
        health_summary = HealthSummaryResponse(
            active_prescriptions_count=active_prescriptions_count,
            active_conditions_count=active_conditions_count,
            last_measurement_date=last_appointment_date,
            pending_exams_count=pending_exam_results_count,
            completed_exams_count=completed_exams_count
        )
        
        return PatientDashboardResponse(
            stats=stats,
            upcoming_appointment=upcoming_appointment,
            recent_activities=recent_activities,
            health_summary=health_summary
        )
    except HTTPException:
        # Re-raise HTTP exceptions (like 403)
        raise
    except Exception as e:
        # Log the error and return a safe response
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_patient_dashboard: {str(e)}", exc_info=True)
        
        # Return empty dashboard on error to prevent frontend crashes
        return PatientDashboardResponse(
            stats=PatientDashboardStats(
                upcoming_appointments_count=0,
                active_prescriptions_count=0,
                pending_exam_results_count=0,
                unread_messages_count=0,
                pending_payments_count=0,
                total_payments_amount=0.0,
                last_appointment_date=None,
                active_conditions_count=0
            ),
            upcoming_appointment=None,
            recent_activities=[],
            health_summary=HealthSummaryResponse(
                active_prescriptions_count=0,
                active_conditions_count=0,
                last_measurement_date=None,
                pending_exams_count=0,
                completed_exams_count=0
            )
        )


# ==================== Individual Data Endpoints ====================

@router.get("/prescriptions", response_model=List[Dict[str, Any]])
async def get_patient_prescriptions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    active_only: bool = False,
):
    """
    Get all prescriptions for the current patient
    """
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for patients"
        )
    
    patient = await get_patient_from_user(current_user, db)
    if not patient:
        return []
    
    # Get all appointments for this patient
    appointments_query = select(Appointment).filter(
        and_(
            Appointment.patient_id == patient.id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    appointments_result = await db.execute(appointments_query)
    appointments = appointments_result.scalars().all()
    appointment_ids = [apt.id for apt in appointments]
    
    if not appointment_ids:
        return []
    
    # Get prescriptions from clinical records
    prescriptions_query = select(Prescription, ClinicalRecord, Appointment, User).join(
        ClinicalRecord, Prescription.clinical_record_id == ClinicalRecord.id
    ).join(
        Appointment, ClinicalRecord.appointment_id == Appointment.id
    ).join(
        User, Appointment.doctor_id == User.id
    ).filter(
        ClinicalRecord.appointment_id.in_(appointment_ids)
    )
    
    if active_only:
        prescriptions_query = prescriptions_query.filter(
            Prescription.is_active == True
        )
    
    prescriptions_query = prescriptions_query.order_by(Prescription.issued_date.desc())
    prescriptions_result = await db.execute(prescriptions_query)
    prescriptions_data = prescriptions_result.all()
    
    result = []
    for presc, record, apt, doctor in prescriptions_data:
        result.append({
            "id": presc.id,
            "medication_name": presc.medication_name,
            "dosage": presc.dosage,
            "frequency": presc.frequency,
            "instructions": presc.instructions,
            "issued_date": presc.issued_date.isoformat() if presc.issued_date else None,
            "duration": presc.duration,
            "is_active": presc.is_active,
            "doctor_name": doctor.full_name,
            "appointment_date": apt.scheduled_datetime.isoformat() if apt.scheduled_datetime else None
        })
    
    return result


@router.get("/exam-results", response_model=List[Dict[str, Any]])
async def get_patient_exam_results(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get all exam results for the current patient
    """
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for patients"
        )
    
    patient = await get_patient_from_user(current_user, db)
    if not patient:
        return []
    
    # Get all appointments for this patient
    appointments_query = select(Appointment).filter(
        and_(
            Appointment.patient_id == patient.id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    appointments_result = await db.execute(appointments_query)
    appointments = appointments_result.scalars().all()
    appointment_ids = [apt.id for apt in appointments]
    
    if not appointment_ids:
        return []
    
    # Get exam requests from clinical records
    exams_query = select(ExamRequest, ClinicalRecord, Appointment, User).join(
        ClinicalRecord, ExamRequest.clinical_record_id == ClinicalRecord.id
    ).join(
        Appointment, ClinicalRecord.appointment_id == Appointment.id
    ).join(
        User, Appointment.doctor_id == User.id
    ).filter(
        ClinicalRecord.appointment_id.in_(appointment_ids)
    ).order_by(ExamRequest.requested_date.desc())
    
    exams_result = await db.execute(exams_query)
    exams_data = exams_result.all()
    
    result = []
    for exam, record, apt, doctor in exams_data:
        # Check if exam has results (completed with description)
        has_result = exam.completed and exam.completed_date is not None
        result_description = exam.description or ""
        has_abnormalities = False
        if result_description:
            result_lower = result_description.lower()
            has_abnormalities = "anormal" in result_lower or "alterado" in result_lower or "alteração" in result_lower
        
        result.append({
            "id": exam.id,
            "exam_type": exam.exam_type,
            "requested_date": exam.requested_date.isoformat() if exam.requested_date else None,
            "completed_date": exam.completed_date.isoformat() if exam.completed_date else None,
            "description": result_description,
            "status": "available" if has_result else "pending",
            "doctor_name": doctor.full_name,
            "appointment_date": apt.scheduled_datetime.isoformat() if apt.scheduled_datetime else None,
            "has_abnormalities": has_abnormalities
        })
    
    return result


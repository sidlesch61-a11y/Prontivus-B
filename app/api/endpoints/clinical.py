"""
Clinical records, prescriptions, and exam requests API endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import joinedload
from fastapi import Body
from fastapi.responses import StreamingResponse
from datetime import datetime, date

from app.core.auth import get_current_user, RoleChecker
from app.models import User, Appointment, Patient, UserRole
from app.models.clinical import ClinicalRecord, Prescription, ExamRequest, Diagnosis, ClinicalRecordVersion, ExamCatalog
from app.schemas.clinical import (
    ClinicalRecordCreate,
    ClinicalRecordUpdate,
    ClinicalRecordResponse,
    ClinicalRecordDetailResponse,
    DiagnosisBase,
    DiagnosisCreate,
    DiagnosisUpdate,
    DiagnosisResponse,
    PrescriptionBase,
    PrescriptionCreate,
    PrescriptionUpdate,
    PrescriptionResponse,
    ExamRequestBase,
    ExamRequestCreate,
    ExamRequestUpdate,
    ExamRequestResponse,
    ExamResultUpdate,
    PatientClinicalHistoryResponse,
    ClinicalRecordVersionResponse,
    ExamCatalogCreate,
    ExamCatalogUpdate,
    ExamCatalogResponse,
    ExamRequestFromAppointmentCreate,
)
from database import get_async_session
from io import BytesIO

router = APIRouter(tags=["Clinical"])

# Role checker for doctors (only doctors can create clinical records)
require_doctor = RoleChecker([UserRole.DOCTOR, UserRole.ADMIN])
require_staff = RoleChecker([UserRole.ADMIN, UserRole.SECRETARY, UserRole.DOCTOR])


# ==================== Exam Catalog (Admin/Secretary) ====================

@router.post("/clinical/exam-catalog", response_model=ExamCatalogResponse, status_code=status.HTTP_201_CREATED)
async def create_exam_catalog_item(
    exam_in: ExamCatalogCreate,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new exam type in the catalog (clinic-scoped).
    """
    db_exam = ExamCatalog(
        clinic_id=current_user.clinic_id,
        **exam_in.model_dump(),
    )
    db.add(db_exam)
    await db.commit()
    await db.refresh(db_exam)
    return ExamCatalogResponse.model_validate(db_exam)


@router.get("/clinical/exam-catalog", response_model=List[ExamCatalogResponse])
async def list_exam_catalog_items(
    search: Optional[str] = Query(None, description="Search by code or name"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List exam catalog items for the current clinic.
    """
    query = select(ExamCatalog).filter(ExamCatalog.clinic_id == current_user.clinic_id)
    if is_active is not None:
        query = query.filter(ExamCatalog.is_active == is_active)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(ExamCatalog.name.ilike(like), ExamCatalog.code.ilike(like)))
    query = query.order_by(ExamCatalog.name)

    result = await db.execute(query)
    exams = result.scalars().all()
    return [ExamCatalogResponse.model_validate(e) for e in exams]


@router.put("/clinical/exam-catalog/{exam_id}", response_model=ExamCatalogResponse)
async def update_exam_catalog_item(
    exam_id: int,
    exam_in: ExamCatalogUpdate,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update an existing exam type in the catalog.
    """
    exam_query = select(ExamCatalog).filter(
        ExamCatalog.id == exam_id,
        ExamCatalog.clinic_id == current_user.clinic_id,
    )
    exam_result = await db.execute(exam_query)
    db_exam = exam_result.scalar_one_or_none()
    if not db_exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")

    update_data = exam_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_exam, field, value)

    await db.commit()
    await db.refresh(db_exam)
    return ExamCatalogResponse.model_validate(db_exam)


@router.delete("/clinical/exam-catalog/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam_catalog_item(
    exam_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Soft-delete an exam from the catalog (marks as inactive).
    """
    exam_query = select(ExamCatalog).filter(
        ExamCatalog.id == exam_id,
        ExamCatalog.clinic_id == current_user.clinic_id,
    )
    exam_result = await db.execute(exam_query)
    db_exam = exam_result.scalar_one_or_none()
    if not db_exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")

    db_exam.is_active = False
    await db.commit()
    return None


# ==================== Exam Requests Management (staff) ====================

@router.get("/clinical/exam-requests", response_model=List[ExamRequestResponse])
async def list_exam_requests_for_clinic(
    status_filter: Optional[str] = Query(
        None,
        description="Filter by status: pending or completed",
        regex="^(pending|completed)$",
    ),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    patient_id: Optional[int] = Query(None),
    appointment_id: Optional[int] = Query(None),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List exam requests for the current clinic so Secretaria/Admin can register results.
    Can also be used by doctors to get exam requests for a specific appointment.
    """
    query = select(ExamRequest).join(ClinicalRecord).join(Appointment).filter(
        Appointment.clinic_id == current_user.clinic_id
    )

    if status_filter == "pending":
        query = query.filter(ExamRequest.completed.is_(False))
    elif status_filter == "completed":
        query = query.filter(ExamRequest.completed.is_(True))

    if date_from:
        query = query.filter(ExamRequest.requested_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(ExamRequest.requested_date <= datetime.combine(date_to, datetime.max.time()))

    if patient_id:
        query = query.filter(Appointment.patient_id == patient_id)

    if appointment_id:
        query = query.filter(ClinicalRecord.appointment_id == appointment_id)

    query = query.order_by(ExamRequest.requested_date.desc())

    result = await db.execute(query)
    exams = result.scalars().all()
    return [ExamRequestResponse.model_validate(e) for e in exams]


@router.put("/clinical/exam-requests/{exam_id}/result", response_model=ExamRequestResponse)
async def update_exam_result(
    exam_id: int,
    payload: ExamResultUpdate,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Register or update exam results (description, completed flag/date, optional link to catalog).
    """
    exam_query = select(ExamRequest).join(ClinicalRecord).join(Appointment).filter(
        ExamRequest.id == exam_id,
        Appointment.clinic_id == current_user.clinic_id,
    )
    exam_result = await db.execute(exam_query)
    exam = exam_result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam request not found")

    data = payload.model_dump(exclude_unset=True)

    # If setting completed without explicit date, default to now
    if data.get("completed") and not data.get("completed_date"):
        data["completed_date"] = datetime.utcnow()

    for field, value in data.items():
        setattr(exam, field, value)

    await db.commit()
    await db.refresh(exam)
    return ExamRequestResponse.model_validate(exam)


@router.delete("/clinical/exam-requests/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam_request(
    exam_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete an exam request (only if it hasn't been completed yet, or allow deletion by staff).
    """
    exam_query = select(ExamRequest).join(ClinicalRecord).join(Appointment).filter(
        ExamRequest.id == exam_id,
        Appointment.clinic_id == current_user.clinic_id,
    )
    exam_result = await db.execute(exam_query)
    exam = exam_result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam request not found")

    await db.delete(exam)
    await db.commit()
    return None


@router.post("/clinical/exam-requests/from-appointment", response_model=ExamRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_exam_request_from_appointment(
    payload: ExamRequestFromAppointmentCreate,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create an exam request linked to an appointment (used by Secretaria / Médico via picklist).
    Will create a minimal ClinicalRecord if none exists yet for that appointment.
    """
    # Verify appointment exists and belongs to clinic
    appt_query = select(Appointment).filter(
        and_(
            Appointment.id == payload.appointment_id,
            Appointment.clinic_id == current_user.clinic_id,
        )
    )
    appt_result = await db.execute(appt_query)
    appointment = appt_result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    # Get or create clinical record for this appointment
    record_query = select(ClinicalRecord).filter(ClinicalRecord.appointment_id == appointment.id)
    record_result = await db.execute(record_query)
    record = record_result.scalar_one_or_none()
    if not record:
        record = ClinicalRecord(appointment_id=appointment.id)
        db.add(record)
        await db.commit()
        await db.refresh(record)

    # Create exam request
    exam = ExamRequest(
        clinical_record_id=record.id,
        exam_type=payload.exam_type,
        description=payload.description,
        reason=payload.reason,
        urgency=payload.urgency,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)

    return ExamRequestResponse.model_validate(exam)
# ==================== Autosave & Version History ====================

@router.post("/appointments/{appointment_id}/clinical-record/autosave")
async def autosave_clinical_record(
    appointment_id: int,
    record_in: ClinicalRecordUpdate,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Autosave partial SOAP note changes as a version snapshot. Does not modify the current record.
    """
    # Ensure appointment belongs to clinic
    appt = (await db.execute(select(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.clinic_id == current_user.clinic_id
    ))).scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    # Ensure record exists
    rec = (await db.execute(select(ClinicalRecord).filter(ClinicalRecord.appointment_id == appointment_id))).scalar_one_or_none()
    if not rec:
        # create a minimal record to attach autosave
        rec = ClinicalRecord(appointment_id=appointment_id)
        db.add(rec)
        await db.commit()
        await db.refresh(rec)

    version = ClinicalRecordVersion(
        clinical_record_id=rec.id,
        author_user_id=current_user.id,
        is_autosave=True,
        snapshot=record_in.model_dump(exclude_unset=True),
    )
    db.add(version)
    await db.commit()
    return {"success": True, "version_id": version.id}


@router.get("/clinical-records/{record_id}/versions", response_model=List[ClinicalRecordVersionResponse])
async def list_versions(
    record_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    versions = (await db.execute(select(ClinicalRecordVersion).filter(ClinicalRecordVersion.clinical_record_id == record_id).order_by(ClinicalRecordVersion.created_at.desc()))).scalars().all()
    return versions



# ==================== Clinical Records ====================

@router.post(
    "/appointments/{appointment_id}/clinical-record",
    response_model=ClinicalRecordDetailResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_or_update_clinical_record(
    appointment_id: int,
    record_in: ClinicalRecordUpdate,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create or update the SOAP note for a specific appointment
    Only the assigned doctor or admins can create/update clinical records
    """
    # Verify appointment exists and belongs to current clinic
    appointment_query = select(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    appointment_result = await db.execute(appointment_query)
    appointment = appointment_result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # Check if current user is the assigned doctor or admin
    if current_user.role != UserRole.ADMIN and appointment.doctor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned doctor can create clinical records for this appointment"
        )
    
    # Check if clinical record already exists
    existing_record_query = select(ClinicalRecord).filter(
        ClinicalRecord.appointment_id == appointment_id
    )
    existing_record_result = await db.execute(existing_record_query)
    existing_record = existing_record_result.scalar_one_or_none()
    
    if existing_record:
        # Update existing record
        update_data = record_in.model_dump(exclude_unset=True)
        # snapshot before update
        pre_snapshot = {
            "subjective": existing_record.subjective,
            "objective": existing_record.objective,
            "assessment": existing_record.assessment,
            "plan": existing_record.plan,
            "plan_soap": getattr(existing_record, "plan_soap", None),
        }
        for field, value in update_data.items():
            setattr(existing_record, field, value)
        
        await db.commit()
        await db.refresh(existing_record)
        
        # Create version snapshot
        version = ClinicalRecordVersion(
            clinical_record_id=existing_record.id,
            author_user_id=current_user.id,
            is_autosave=False,
            snapshot=pre_snapshot,
        )
        db.add(version)
        await db.commit()
        
        # Reload with relationships
        record_query = select(ClinicalRecord).options(
            joinedload(ClinicalRecord.prescriptions),
            joinedload(ClinicalRecord.exam_requests),
            joinedload(ClinicalRecord.diagnoses)
        ).filter(ClinicalRecord.id == existing_record.id)
        
        record_result = await db.execute(record_query)
        loaded_record = record_result.unique().scalar_one()
        
        return loaded_record
    else:
        # Create new record
        db_record = ClinicalRecord(
            appointment_id=appointment_id,
            **record_in.model_dump(exclude_unset=True)
        )
        db.add(db_record)
        await db.commit()
        await db.refresh(db_record)
        
        # Reload with relationships
        record_query = select(ClinicalRecord).options(
            joinedload(ClinicalRecord.prescriptions),
            joinedload(ClinicalRecord.exam_requests),
            joinedload(ClinicalRecord.diagnoses)
        ).filter(ClinicalRecord.id == db_record.id)
        
        record_result = await db.execute(record_query)
        loaded_record = record_result.unique().scalar_one()
        
        return loaded_record


@router.get(
    "/appointments/{appointment_id}/clinical-record",
    response_model=Optional[ClinicalRecordDetailResponse]
)
async def get_appointment_clinical_record(
    appointment_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get the clinical record for a specific appointment.
    Returns null if no clinical record exists yet.
    """
    # Verify appointment exists and belongs to current clinic
    appointment_query = select(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    appointment_result = await db.execute(appointment_query)
    appointment = appointment_result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # Get clinical record with relationships
    record_query = select(ClinicalRecord).options(
        joinedload(ClinicalRecord.prescriptions),
        joinedload(ClinicalRecord.exam_requests),
        joinedload(ClinicalRecord.diagnoses)
    ).filter(ClinicalRecord.appointment_id == appointment_id)
    
    record_result = await db.execute(record_query)
    record = record_result.unique().scalar_one_or_none()
    
    # Return null if no record exists (instead of 404)
    return record


@router.get(
    "/patients/{patient_id}/clinical-records",
    response_model=List[PatientClinicalHistoryResponse]
)
async def get_patient_clinical_history(
    patient_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get a patient's complete clinical history
    Returns all appointments with their clinical records, prescriptions, and exam requests
    """
    # Verify patient exists and belongs to current clinic
    patient_query = select(Patient).filter(
        Patient.id == patient_id,
        Patient.clinic_id == current_user.clinic_id
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    # Get all appointments with clinical records
    appointments_query = select(Appointment, User, ClinicalRecord).join(
        User, Appointment.doctor_id == User.id
    ).outerjoin(
        ClinicalRecord, Appointment.id == ClinicalRecord.appointment_id
    ).filter(
        Appointment.patient_id == patient_id,
        Appointment.clinic_id == current_user.clinic_id
    ).order_by(Appointment.scheduled_datetime.desc())
    
    appointments_result = await db.execute(appointments_query)
    appointments_data = appointments_result.all()
    
    history = []
    for appointment, doctor, clinical_record in appointments_data:
        # Load prescriptions and exam requests if clinical record exists
        clinical_record_detail = None
        if clinical_record:
            # Reload with relationships
            record_query = select(ClinicalRecord).options(
                joinedload(ClinicalRecord.prescriptions),
                joinedload(ClinicalRecord.exam_requests),
                joinedload(ClinicalRecord.diagnoses)
            ).filter(ClinicalRecord.id == clinical_record.id)
            record_result = await db.execute(record_query)
            clinical_record_detail = record_result.scalar_one()
        
        history.append(PatientClinicalHistoryResponse(
            appointment_id=appointment.id,
            appointment_date=appointment.scheduled_datetime,
            doctor_name=f"{doctor.first_name} {doctor.last_name}",
            appointment_type=appointment.appointment_type,
            clinical_record=ClinicalRecordDetailResponse.model_validate(clinical_record_detail) if clinical_record_detail else None
        ))
    
    return history


@router.get(
    "/clinical/me/history",
    response_model=List[PatientClinicalHistoryResponse]
)
async def get_my_clinical_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Patient self-access to their clinical history (appointments + clinical records with prescriptions and exam requests).
    Maps the authenticated user to a Patient by email and clinic.
    """
    try:
        if current_user.role != UserRole.PATIENT:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only patients can access their own clinical history")

        # Map user to patient by email
        pat_q = select(Patient).where(Patient.email == current_user.email, Patient.clinic_id == current_user.clinic_id)
        pat_res = await db.execute(pat_q)
        patient = pat_res.scalar_one_or_none()
        if not patient:
            return []

        appts_q = select(Appointment, User, ClinicalRecord).join(
            User, Appointment.doctor_id == User.id
        ).outerjoin(
            ClinicalRecord, Appointment.id == ClinicalRecord.appointment_id
        ).where(
            Appointment.patient_id == patient.id,
            Appointment.clinic_id == current_user.clinic_id
        ).order_by(Appointment.scheduled_datetime.desc())

        appts_res = await db.execute(appts_q)
        appts = appts_res.all()

        out: list[PatientClinicalHistoryResponse] = []
        for appointment, doctor, clinical_record in appts:
            record_detail = None
            if clinical_record:
                try:
                    rq = select(ClinicalRecord).options(
                        joinedload(ClinicalRecord.prescriptions),
                        joinedload(ClinicalRecord.exam_requests),
                        joinedload(ClinicalRecord.diagnoses)
                    ).where(ClinicalRecord.id == clinical_record.id)
                    rr = await db.execute(rq)
                    record_detail = rr.scalar_one_or_none()
                except Exception as e:
                    # Log error but continue with other records
                    import logging
                    logging.error(f"Error loading clinical record {clinical_record.id}: {str(e)}")
                    record_detail = None

            try:
                clinical_record_response = None
                if record_detail:
                    try:
                        clinical_record_response = ClinicalRecordDetailResponse.model_validate(record_detail)
                    except Exception as e:
                        # If validation fails, try to create a basic response without relationships
                        import logging
                        logging.error(f"Error validating clinical record {record_detail.id}: {str(e)}")
                        # Create a basic response with empty relationships
                        clinical_record_response = ClinicalRecordDetailResponse(
                            id=record_detail.id,
                            appointment_id=record_detail.appointment_id,
                            subjective=record_detail.subjective,
                            objective=record_detail.objective,
                            assessment=record_detail.assessment,
                            plan=record_detail.plan,
                            plan_soap=record_detail.plan_soap,
                            created_at=record_detail.created_at,
                            updated_at=record_detail.updated_at,
                            prescriptions=[],
                            exam_requests=[],
                            diagnoses=[]
                        )

                out.append(PatientClinicalHistoryResponse(
                    appointment_id=appointment.id,
                    appointment_date=appointment.scheduled_datetime,
                    doctor_name=f"{doctor.first_name} {doctor.last_name}",
                    appointment_type=appointment.appointment_type,
                    status=appointment.status,
                    clinical_record=clinical_record_response
                ))
            except Exception as e:
                # Log error but continue with other appointments
                import logging
                logging.error(f"Error processing appointment {appointment.id}: {str(e)}")
                continue

        return out
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error in get_my_clinical_history: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading clinical history: {str(e)}"
        )


@router.get(
    "/clinical/doctor/my-clinical-records",
    response_model=List[PatientClinicalHistoryResponse]
)
async def get_my_doctor_clinical_records(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """
    Get all clinical records for the current doctor
    Returns appointments with their clinical records, filtered by doctor_id
    """
    # Only allow doctors to access this endpoint
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for doctors"
        )
    
    # Get all appointments for this doctor with clinical records
    appointments_query = select(Appointment, Patient, User, ClinicalRecord).join(
        Patient, Appointment.patient_id == Patient.id
    ).join(
        User, Appointment.doctor_id == User.id
    ).outerjoin(
        ClinicalRecord, Appointment.id == ClinicalRecord.appointment_id
    ).filter(
        and_(
            Appointment.doctor_id == current_user.id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    
    # Apply date filters
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        appointments_query = appointments_query.filter(Appointment.scheduled_datetime >= start_datetime)
    
    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time())
        appointments_query = appointments_query.filter(Appointment.scheduled_datetime <= end_datetime)
    
    # Apply search filter
    if search:
        search_filter = or_(
            Patient.first_name.ilike(f"%{search}%"),
            Patient.last_name.ilike(f"%{search}%"),
            Patient.email.ilike(f"%{search}%"),
            Appointment.appointment_type.ilike(f"%{search}%")
        )
        appointments_query = appointments_query.filter(search_filter)
    
    appointments_query = appointments_query.order_by(Appointment.scheduled_datetime.desc())
    appointments_query = appointments_query.offset(skip).limit(limit)
    
    appointments_result = await db.execute(appointments_query)
    appointments_data = appointments_result.all()
    
    records = []
    for appointment, patient, doctor, clinical_record in appointments_data:
        # Load clinical record with relationships if it exists
        clinical_record_detail = None
        if clinical_record:
            record_query = select(ClinicalRecord).options(
                joinedload(ClinicalRecord.prescriptions),
                joinedload(ClinicalRecord.exam_requests),
                joinedload(ClinicalRecord.diagnoses)
            ).filter(ClinicalRecord.id == clinical_record.id)
            record_result = await db.execute(record_query)
            clinical_record_detail = record_result.unique().scalar_one()
        
        # Get patient full name
        patient_name = f"{patient.first_name or ''} {patient.last_name or ''}".strip()
        if not patient_name:
            patient_name = patient.email or "Paciente"
        
        # Get status as string
        appointment_status = appointment.status.value if hasattr(appointment.status, 'value') else str(appointment.status)
        
        records.append(PatientClinicalHistoryResponse(
            appointment_id=appointment.id,
            appointment_date=appointment.scheduled_datetime,
            doctor_name=f"{doctor.first_name} {doctor.last_name}".strip() or doctor.username or "Médico",
            patient_name=patient_name,
            appointment_type=appointment.appointment_type,
            status=appointment_status,
            clinical_record=ClinicalRecordDetailResponse.model_validate(clinical_record_detail) if clinical_record_detail else None
        ))
    
    return records


# ==================== Prescriptions ====================

@router.get(
    "/clinical-records/{clinical_record_id}/prescriptions",
    response_model=List[PrescriptionResponse]
)
async def get_prescriptions_by_clinical_record(
    clinical_record_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get all prescriptions for a specific clinical record
    """
    # Verify clinical record exists and belongs to current clinic
    record_query = select(ClinicalRecord).filter(
        ClinicalRecord.id == clinical_record_id
    )
    record_result = await db.execute(record_query)
    clinical_record = record_result.scalar_one_or_none()
    
    if not clinical_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical record not found"
        )
    
    # Verify appointment belongs to clinic
    appointment_query = select(Appointment).filter(
        Appointment.id == clinical_record.appointment_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    appointment_result = await db.execute(appointment_query)
    appointment = appointment_result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # Get prescriptions
    prescriptions_query = select(Prescription).filter(
        Prescription.clinical_record_id == clinical_record_id
    ).order_by(Prescription.created_at.desc())
    
    prescriptions_result = await db.execute(prescriptions_query)
    prescriptions = prescriptions_result.scalars().all()
    
    return prescriptions


@router.post(
    "/clinical-records/{clinical_record_id}/prescriptions",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_prescription(
    clinical_record_id: int,
    prescription_in: PrescriptionBase,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new prescription for a clinical record
    """
    # Verify clinical record exists and belongs to current clinic
    record_query = select(ClinicalRecord).filter(
        ClinicalRecord.id == clinical_record_id
    )
    record_result = await db.execute(record_query)
    clinical_record = record_result.scalar_one_or_none()
    
    if not clinical_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical record not found"
        )
    
    # Verify appointment belongs to clinic
    appointment_query = select(Appointment).filter(
        Appointment.id == clinical_record.appointment_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    appointment_result = await db.execute(appointment_query)
    appointment = appointment_result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # Check if current user is the assigned doctor or admin
    if current_user.role != UserRole.ADMIN and appointment.doctor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned doctor can create prescriptions for this appointment"
        )
    
    # Create prescription
    prescription_data = prescription_in.model_dump()
    prescription = Prescription(
        clinical_record_id=clinical_record_id,
        **prescription_data
    )
    db.add(prescription)
    await db.commit()
    await db.refresh(prescription)
    
    return prescription


@router.get(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionResponse
)
async def get_prescription(
    prescription_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get a single prescription by ID
    """
    # Get prescription with clinical record and appointment
    prescription_query = select(Prescription).join(
        ClinicalRecord
    ).join(
        Appointment
    ).filter(
        Prescription.id == prescription_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    
    prescription_result = await db.execute(prescription_query)
    prescription = prescription_result.scalar_one_or_none()
    
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    return prescription


@router.put(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionResponse
)
async def update_prescription(
    prescription_id: int,
    prescription_in: PrescriptionUpdate,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update a prescription
    """
    # Get prescription with clinical record and appointment
    prescription_query = select(Prescription).join(
        ClinicalRecord
    ).join(
        Appointment
    ).filter(
        Prescription.id == prescription_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    
    prescription_result = await db.execute(prescription_query)
    prescription = prescription_result.scalar_one_or_none()
    
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    # Get appointment to check doctor assignment
    # Get clinical record first to access appointment_id
    clinical_record_id = prescription.clinical_record_id
    clinical_record_query = select(ClinicalRecord).filter(
        ClinicalRecord.id == clinical_record_id
    )
    clinical_record_result = await db.execute(clinical_record_query)
    clinical_record = clinical_record_result.scalar_one_or_none()
    
    if not clinical_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical record not found"
        )
    
    appointment_query = select(Appointment).filter(
        Appointment.id == clinical_record.appointment_id
    )
    appointment_result = await db.execute(appointment_query)
    appointment = appointment_result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # Check if current user is the assigned doctor or admin
    if current_user.role != UserRole.ADMIN and appointment.doctor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned doctor can update prescriptions for this appointment"
        )
    
    # Update prescription
    update_data = prescription_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prescription, field, value)
    
    await db.commit()
    await db.refresh(prescription)
    
    return prescription


@router.delete(
    "/prescriptions/{prescription_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_prescription(
    prescription_id: int,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete a prescription
    """
    # Get prescription with clinical record and appointment
    prescription_query = select(Prescription).join(
        ClinicalRecord
    ).join(
        Appointment
    ).filter(
        Prescription.id == prescription_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    
    prescription_result = await db.execute(prescription_query)
    prescription = prescription_result.scalar_one_or_none()
    
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    # Get appointment to check doctor assignment
    # Get clinical record first to access appointment_id
    clinical_record_id = prescription.clinical_record_id
    clinical_record_query = select(ClinicalRecord).filter(
        ClinicalRecord.id == clinical_record_id
    )
    clinical_record_result = await db.execute(clinical_record_query)
    clinical_record = clinical_record_result.scalar_one_or_none()
    
    if not clinical_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical record not found"
        )
    
    appointment_query = select(Appointment).filter(
        Appointment.id == clinical_record.appointment_id
    )
    appointment_result = await db.execute(appointment_query)
    appointment = appointment_result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # Check if current user is the assigned doctor or admin
    if current_user.role != UserRole.ADMIN and appointment.doctor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned doctor can delete prescriptions for this appointment"
        )
    
    # Delete prescription
    await db.delete(prescription)
    await db.commit()
    
    return None


# ==================== Exam Requests ====================

@router.get(
    "/clinical-records/{clinical_record_id}/exam-requests",
    response_model=List[ExamRequestResponse]
)
async def get_exam_requests_by_clinical_record(
    clinical_record_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get all exam requests for a specific clinical record
    """
    # Verify clinical record exists and belongs to current clinic
    record_query = select(ClinicalRecord).filter(
        ClinicalRecord.id == clinical_record_id
    )
    record_result = await db.execute(record_query)
    clinical_record = record_result.scalar_one_or_none()
    
    if not clinical_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical record not found"
        )
    
    # Verify appointment belongs to clinic
    appointment_query = select(Appointment).filter(
        Appointment.id == clinical_record.appointment_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    appointment_result = await db.execute(appointment_query)
    appointment = appointment_result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # Get exam requests
    exam_requests_query = select(ExamRequest).filter(
        ExamRequest.clinical_record_id == clinical_record_id
    ).order_by(ExamRequest.created_at.desc())
    
    exam_requests_result = await db.execute(exam_requests_query)
    exam_requests = exam_requests_result.scalars().all()
    
    return exam_requests


@router.post(
    "/clinical-records/{clinical_record_id}/exam-requests",
    response_model=ExamRequestResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_exam_request(
    clinical_record_id: int,
    exam_request_in: ExamRequestBase,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new exam request for a clinical record
    """
    # Verify clinical record exists and belongs to current clinic
    record_query = select(ClinicalRecord).filter(
        ClinicalRecord.id == clinical_record_id
    )
    record_result = await db.execute(record_query)
    clinical_record = record_result.scalar_one_or_none()
    
    if not clinical_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical record not found"
        )
    
    # Verify appointment belongs to clinic
    appointment_query = select(Appointment).filter(
        Appointment.id == clinical_record.appointment_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    appointment_result = await db.execute(appointment_query)
    appointment = appointment_result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # Check if current user is the assigned doctor or admin
    if current_user.role != UserRole.ADMIN and appointment.doctor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned doctor can create exam requests for this appointment"
        )
    
    # Create exam request
    exam_request_data = exam_request_in.model_dump()
    exam_request = ExamRequest(
        clinical_record_id=clinical_record_id,
        **exam_request_data
    )
    db.add(exam_request)
    await db.commit()
    await db.refresh(exam_request)
    
    return exam_request
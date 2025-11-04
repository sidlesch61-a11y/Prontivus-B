"""
Clinical records, prescriptions, and exam requests API endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from fastapi import Body
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_user, RoleChecker
from app.models import User, Appointment, Patient, UserRole
from app.models.clinical import ClinicalRecord, Prescription, ExamRequest, Diagnosis, ClinicalRecordVersion
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
    PatientClinicalHistoryResponse,
    ClinicalRecordVersionResponse,
)
from database import get_async_session
from io import BytesIO

router = APIRouter(tags=["Clinical"])

# Role checker for doctors (only doctors can create clinical records)
require_doctor = RoleChecker([UserRole.DOCTOR, UserRole.ADMIN])
require_staff = RoleChecker([UserRole.ADMIN, UserRole.SECRETARY, UserRole.DOCTOR])
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
        # store version snapshot
        version = ClinicalRecordVersion(
            clinical_record_id=existing_record.id,
            author_user_id=current_user.id,
            is_autosave=False,
            snapshot=pre_snapshot,
        )
        db.add(version)
        await db.commit()
        
        # Re-query with eager loading to properly load relationships
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
        
        # Re-query with eager loading to properly load relationships
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
    
    # Build response
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


# ==================== Prescriptions ====================

@router.post(
    "/clinical-records/{record_id}/prescriptions",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_201_CREATED
)
async def add_prescription(
    record_id: int,
    prescription_in: PrescriptionBase,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Add a prescription to a clinical record
    """
    # Verify clinical record exists and belongs to doctor's clinic
    record_query = select(ClinicalRecord).join(
        Appointment, ClinicalRecord.appointment_id == Appointment.id
    ).filter(
        ClinicalRecord.id == record_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    record_result = await db.execute(record_query)
    record = record_result.scalar_one_or_none()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical record not found"
        )
    
    # Create prescription
    db_prescription = Prescription(
        clinical_record_id=record_id,
        **prescription_in.model_dump(exclude_unset=True)
    )
    db.add(db_prescription)
    await db.commit()
    await db.refresh(db_prescription)
    
    return db_prescription


@router.get(
    "/clinical-records/{record_id}/prescriptions",
    response_model=List[PrescriptionResponse]
)
async def list_prescriptions(
    record_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all prescriptions for a clinical record
    """
    prescriptions_query = select(Prescription).filter(
        Prescription.clinical_record_id == record_id
    ).order_by(Prescription.issued_date.desc())
    
    prescriptions_result = await db.execute(prescriptions_query)
    prescriptions = prescriptions_result.scalars().all()
    
    return prescriptions


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
    prescription_query = select(Prescription).filter(Prescription.id == prescription_id)
    prescription_result = await db.execute(prescription_query)
    db_prescription = prescription_result.scalar_one_or_none()
    
    if not db_prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    # Update fields
    update_data = prescription_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_prescription, field, value)
    
    await db.commit()
    await db.refresh(db_prescription)
    
    return db_prescription


@router.delete("/prescriptions/{prescription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prescription(
    prescription_id: int,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete a prescription
    """
    prescription_query = select(Prescription).filter(Prescription.id == prescription_id)
    prescription_result = await db.execute(prescription_query)
    db_prescription = prescription_result.scalar_one_or_none()
    
    if not db_prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    await db.delete(db_prescription)
    await db.commit()
    
    return None


# ==================== Exam Requests ====================

@router.post(
    "/clinical-records/{record_id}/exam-requests",
    response_model=ExamRequestResponse,
    status_code=status.HTTP_201_CREATED
)
async def add_exam_request(
    record_id: int,
    exam_request_in: ExamRequestBase,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Add an exam request to a clinical record
    """
    # Verify clinical record exists and belongs to doctor's clinic
    record_query = select(ClinicalRecord).join(
        Appointment, ClinicalRecord.appointment_id == Appointment.id
    ).filter(
        ClinicalRecord.id == record_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    record_result = await db.execute(record_query)
    record = record_result.scalar_one_or_none()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical record not found"
        )
    
    # Create exam request
    db_exam_request = ExamRequest(
        clinical_record_id=record_id,
        **exam_request_in.model_dump(exclude_unset=True)
    )
    db.add(db_exam_request)
    await db.commit()
    await db.refresh(db_exam_request)
    
    return db_exam_request


@router.get(
    "/clinical-records/{record_id}/exam-requests",
    response_model=List[ExamRequestResponse]
)
async def list_exam_requests(
    record_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all exam requests for a clinical record
    """
    exam_requests_query = select(ExamRequest).filter(
        ExamRequest.clinical_record_id == record_id
    ).order_by(ExamRequest.requested_date.desc())
    
    exam_requests_result = await db.execute(exam_requests_query)
    exam_requests = exam_requests_result.scalars().all()
    
    return exam_requests


@router.put(
    "/exam-requests/{exam_request_id}",
    response_model=ExamRequestResponse
)
async def update_exam_request(
    exam_request_id: int,
    exam_request_in: ExamRequestUpdate,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update an exam request
    """
    exam_request_query = select(ExamRequest).filter(ExamRequest.id == exam_request_id)
    exam_request_result = await db.execute(exam_request_query)
    db_exam_request = exam_request_result.scalar_one_or_none()
    
    if not db_exam_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam request not found"
        )
    
    # Update fields
    update_data = exam_request_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_exam_request, field, value)
    
    await db.commit()
    await db.refresh(db_exam_request)
    
    return db_exam_request


@router.delete("/exam-requests/{exam_request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam_request(
    exam_request_id: int,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete an exam request
    """
    exam_request_query = select(ExamRequest).filter(ExamRequest.id == exam_request_id)
    exam_request_result = await db.execute(exam_request_query)
    db_exam_request = exam_request_result.scalar_one_or_none()
    
    if not db_exam_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam request not found"
        )
    
    await db.delete(db_exam_request)
    await db.commit()
    
    return None


###################### Diagnoses ######################

@router.post(
    "/clinical-records/{record_id}/diagnoses",
    response_model=DiagnosisResponse,
    status_code=status.HTTP_201_CREATED
)
async def add_diagnosis(
    record_id: int,
    diagnosis_in: DiagnosisBase,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Add a diagnosis (ICD-10) to a clinical record
    """
    # Verify clinical record exists under clinic
    record_query = select(ClinicalRecord).join(
        Appointment, ClinicalRecord.appointment_id == Appointment.id
    ).filter(
        ClinicalRecord.id == record_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    record = (await db.execute(record_query)).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinical record not found")

    db_dx = Diagnosis(
        clinical_record_id=record_id,
        **diagnosis_in.model_dump(exclude_unset=True)
    )
    db.add(db_dx)
    await db.commit()
    await db.refresh(db_dx)
    return db_dx


@router.get(
    "/clinical-records/{record_id}/diagnoses",
    response_model=List[DiagnosisResponse]
)
async def list_diagnoses(
    record_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    query = select(Diagnosis).filter(Diagnosis.clinical_record_id == record_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.put(
    "/diagnoses/{diagnosis_id}",
    response_model=DiagnosisResponse
)
async def update_diagnosis(
    diagnosis_id: int,
    diagnosis_in: DiagnosisUpdate,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    query = select(Diagnosis).filter(Diagnosis.id == diagnosis_id)
    dx = (await db.execute(query)).scalar_one_or_none()
    if not dx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found")
    for field, value in diagnosis_in.model_dump(exclude_unset=True).items():
        setattr(dx, field, value)
    await db.commit()
    await db.refresh(dx)
    return dx


@router.delete("/diagnoses/{diagnosis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_diagnosis(
    diagnosis_id: int,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    query = select(Diagnosis).filter(Diagnosis.id == diagnosis_id)
    dx = (await db.execute(query)).scalar_one_or_none()
    if not dx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found")
    await db.delete(dx)
    await db.commit()
    return None


###################### Decision Support ######################

@router.get("/icd10/suggest")
async def suggest_icd10(
    symptoms: str,
    current_user: User = Depends(require_staff),
):
    """
    Very simple rule-based ICD-10 suggestions from keywords. Replace with ML or external service later.
    """
    s = symptoms.lower()
    suggestions = []
    rules = [
        ("dor de cabeça", [
            {"code": "R51.9", "description": "Cefaleia, não especificada"},
            {"code": "G43.9", "description": "Enxaqueca, não especificada"},
        ]),
        ("febre", [
            {"code": "R50.9", "description": "Febre, não especificada"},
        ]),
        ("tosse", [
            {"code": "R05", "description": "Tosse"},
            {"code": "J06.9", "description": "Infecção aguda das vias aéreas superiores, não especificada"},
        ]),
        ("dor torácica", [
            {"code": "R07.4", "description": "Dor torácica, não especificada"},
        ]),
    ]
    for key, items in rules:
        if key in s:
            suggestions.extend(items)
    return suggestions[:10]


@router.post("/drug-interactions/check")
async def check_drug_interactions(
    payload: dict = Body(...),
    current_user: User = Depends(require_doctor),
):
    """
    Basic interaction checker placeholder. Expects payload = { medications: ["drug a", "drug b", ...] }
    Returns potential interactions based on a tiny static rule set.
    """
    meds = [m.lower().strip() for m in payload.get("medications", []) if isinstance(m, str)]
    interactions = []
    rules = [
        ({"ibuprofeno", "enalapril"}, "Risco de redução do efeito anti-hipertensivo"),
        ({"warfarina", "amoxicilina"}, "Possível aumento do INR; monitorar"),
        ({"sertralina", "tramadol"}, "Risco de síndrome serotoninérgica"),
    ]
    set_meds = set(meds)
    for pair, note in rules:
        if len(pair & set_meds) == len(pair):
            interactions.append({"pair": list(pair), "severity": "moderate", "note": note})
    return {"interactions": interactions}


###################### PDF Generation ######################

def _pdf_bytes(content: str) -> bytes:
    # Minimal placeholder PDF generator using reportlab if available; fallback to simple bytes
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 50
        for line in content.split("\n"):
            c.drawString(40, y, line[:120])
            y -= 18
            if y < 50:
                c.showPage()
                y = height - 50
        c.showPage()
        c.save()
        buffer.seek(0)
        return buffer.read()
    except Exception:
        return content.encode("utf-8")


@router.get("/prescriptions/{prescription_id}/pdf")
async def generate_prescription_pdf(
    prescription_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    q = await db.execute(select(Prescription, ClinicalRecord, Appointment, User).join(
        ClinicalRecord, Prescription.clinical_record_id == ClinicalRecord.id
    ).join(Appointment, ClinicalRecord.appointment_id == Appointment.id).join(User, Appointment.doctor_id == User.id).filter(
        Prescription.id == prescription_id,
        Appointment.clinic_id == current_user.clinic_id
    ))
    row = q.first()
    if not row:
        raise HTTPException(status_code=404, detail="Prescription not found")
    prescription, record, appt, doctor = row
    content = f"Clinica: {doctor.clinic_id}\n\nPrescrição\nPaciente: {appt.patient_id}\nMédico: {doctor.first_name} {doctor.last_name} - CRM\n\n" \
              f"Medicamento: {prescription.medication_name}\nDose: {prescription.dosage}\nFrequência: {prescription.frequency}\n" \
              f"Duração: {prescription.duration or ''}\nInstruções: {prescription.instructions or ''}\nData: {prescription.issued_date}"
    pdf = _pdf_bytes(content)
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf", headers={"Content-Disposition": f"inline; filename=prescription_{prescription_id}.pdf"})


@router.get("/appointments/{appointment_id}/certificate/pdf")
async def generate_certificate_pdf(
    appointment_id: int,
    text: str = "Paciente esteve em atendimento médico.",
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    appt = (await db.execute(select(Appointment, User).join(User, Appointment.doctor_id == User.id).filter(
        Appointment.id == appointment_id,
        Appointment.clinic_id == current_user.clinic_id
    ))).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    appointment, doctor = appt
    content = f"Atestado Médico\n\nPaciente ID: {appointment.patient_id}\nData: {appointment.scheduled_datetime}\n\n{text}\n\nAssinatura: {doctor.first_name} {doctor.last_name} - CRM"
    pdf = _pdf_bytes(content)
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf", headers={"Content-Disposition": f"inline; filename=certificate_{appointment_id}.pdf"})


@router.get("/clinical-records/{record_id}/referral/pdf")
async def generate_referral_pdf(
    record_id: int,
    specialty: str = "",
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session),
):
    rec = (await db.execute(select(ClinicalRecord, Appointment, User).join(
        Appointment, ClinicalRecord.appointment_id == Appointment.id
    ).join(User, Appointment.doctor_id == User.id).filter(
        ClinicalRecord.id == record_id,
        Appointment.clinic_id == current_user.clinic_id
    ))).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Clinical record not found")
    record, appointment, doctor = rec
    content = f"Encaminhamento\n\nEspecialidade: {specialty}\nPaciente ID: {appointment.patient_id}\n\nMotivo: {record.assessment or ''}\n\nAssinatura: {doctor.first_name} {doctor.last_name} - CRM"
    pdf = _pdf_bytes(content)
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf", headers={"Content-Disposition": f"inline; filename=referral_{record_id}.pdf"})

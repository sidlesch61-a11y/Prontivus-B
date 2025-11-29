"""
PDF Document Generation API Endpoints
Handles generation and download of PDF documents (consultations, prescriptions, certificates)
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload

from database import get_async_session
from app.core.auth import get_current_user, RoleChecker
from app.models import User, Appointment, Patient, Clinic, UserRole
from app.models.clinical import ClinicalRecord, Prescription, Diagnosis, ExamRequest
from app.services.pdf_generator import PDFGenerator, generate_prescription_pdf, generate_medical_certificate_pdf

router = APIRouter(prefix="/documents", tags=["Documents"])
pdf_generator = PDFGenerator()

# Role checkers
require_doctor = RoleChecker([UserRole.DOCTOR, UserRole.ADMIN])
require_staff = RoleChecker([UserRole.ADMIN, UserRole.SECRETARY, UserRole.DOCTOR])


async def _get_consultation_data(
    appointment_id: int,
    current_user: User,
    db: AsyncSession
) -> dict:
    """
    Fetch complete consultation data for PDF generation
    
    Returns:
        Dictionary with clinic, patient, doctor, appointment, clinical_record, 
        prescriptions, diagnoses, exam_requests
    """
    # Get appointment with relationships
    appointment_query = select(Appointment).options(
        selectinload(Appointment.patient),
        selectinload(Appointment.doctor),
        selectinload(Appointment.clinic),
        selectinload(Appointment.clinical_record).selectinload(ClinicalRecord.prescriptions),
        selectinload(Appointment.clinical_record).selectinload(ClinicalRecord.diagnoses),
        selectinload(Appointment.clinical_record).selectinload(ClinicalRecord.exam_requests),
    ).filter(
        Appointment.id == appointment_id,
        Appointment.clinic_id == current_user.clinic_id
    )
    
    result = await db.execute(appointment_query)
    appointment = result.unique().scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    # Check access permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.DOCTOR, UserRole.SECRETARY]:
        if current_user.role == UserRole.PATIENT and appointment.patient_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    
    # Build consultation data dictionary
    clinical_record = appointment.clinical_record
    
    consultation_data = {
        'clinic': {
            'name': appointment.clinic.name if appointment.clinic else 'Prontivus Clinic',
            'address': appointment.clinic.address if appointment.clinic else '',
            'phone': appointment.clinic.phone if appointment.clinic else '',
            'email': appointment.clinic.email if appointment.clinic else '',
            # CNPJ/CPF da clínica para cabeçalho dos documentos
            'tax_id': appointment.clinic.tax_id if appointment.clinic else '',
        },
        'patient': {
            'first_name': appointment.patient.first_name if appointment.patient else '',
            'last_name': appointment.patient.last_name if appointment.patient else '',
            'cpf': appointment.patient.cpf if appointment.patient else '',
            'date_of_birth': appointment.patient.date_of_birth.strftime('%d/%m/%Y') if appointment.patient and appointment.patient.date_of_birth else '',
            'gender': appointment.patient.gender.value if appointment.patient and appointment.patient.gender else '',
            'phone': appointment.patient.phone if appointment.patient else '',
            'email': appointment.patient.email if appointment.patient else '',
            'address': appointment.patient.address if appointment.patient else '',
        },
        'doctor': {
            'first_name': appointment.doctor.first_name if appointment.doctor else '',
            'last_name': appointment.doctor.last_name if appointment.doctor else '',
            'crm': getattr(appointment.doctor, 'crm', '') or '',
            'name': f"{appointment.doctor.first_name or ''} {appointment.doctor.last_name or ''}".strip() if appointment.doctor else '',
        },
        'appointment': {
            'scheduled_datetime': appointment.scheduled_datetime,
            'appointment_type': appointment.appointment_type or '',
            'status': appointment.status.value if hasattr(appointment.status, 'value') else str(appointment.status),
            'reason': appointment.reason or '',
        },
        'clinical_record': None,
        'prescriptions': [],
        'diagnoses': [],
        'exam_requests': [],
    }
    
    if clinical_record:
        consultation_data['clinical_record'] = {
            'subjective': clinical_record.subjective or '',
            'objective': clinical_record.objective or '',
            'assessment': clinical_record.assessment or '',
            'plan': clinical_record.plan or '',
            'plan_soap': clinical_record.plan_soap or '',
        }
        
        # Prescriptions
        if clinical_record.prescriptions:
            consultation_data['prescriptions'] = [
                {
                    'medication_name': rx.medication_name,
                    'dosage': rx.dosage,
                    'frequency': rx.frequency,
                    'duration': rx.duration or '',
                    'instructions': rx.instructions or '',
                }
                for rx in clinical_record.prescriptions
            ]
        
        # Diagnoses
        if clinical_record.diagnoses:
            consultation_data['diagnoses'] = [
                {
                    'icd10_code': dx.cid_code or '',  # CID code is ICD-10 code
                    'description': dx.description or '',
                    'diagnosis': dx.description or '',
                }
                for dx in clinical_record.diagnoses
            ]
        
        # Exam Requests
        if clinical_record.exam_requests:
            consultation_data['exam_requests'] = [
                {
                    'exam_type': er.exam_type,
                    'description': er.description or '',
                    'reason': er.reason or '',
                    'urgency': er.urgency.value if hasattr(er.urgency, 'value') else str(er.urgency),
                }
                for er in clinical_record.exam_requests
            ]
    
    return consultation_data


async def _get_prescription_data(
    prescription_id: int,
    current_user: User,
    db: AsyncSession
) -> dict:
    """
    Fetch prescription data for PDF generation
    """
    prescription_query = select(Prescription).options(
        selectinload(Prescription.clinical_record).selectinload(ClinicalRecord.appointment).selectinload(Appointment.patient),
        selectinload(Prescription.clinical_record).selectinload(ClinicalRecord.appointment).selectinload(Appointment.doctor),
        selectinload(Prescription.clinical_record).selectinload(ClinicalRecord.appointment).selectinload(Appointment.clinic),
    ).filter(Prescription.id == prescription_id)
    
    result = await db.execute(prescription_query)
    prescription = result.unique().scalar_one_or_none()
    
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    appointment = prescription.clinical_record.appointment
    
    # Check access
    if current_user.role not in [UserRole.ADMIN, UserRole.DOCTOR, UserRole.SECRETARY]:
        if current_user.role == UserRole.PATIENT and appointment.patient_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    
    clinic = appointment.clinic
    patient = appointment.patient
    doctor = appointment.doctor
    
    prescription_data = {
        'clinic': {
            'name': clinic.name if clinic else 'Prontivus Clinic',
            'address': clinic.address if clinic else '',
            'phone': clinic.phone if clinic else '',
            'email': clinic.email if clinic else '',
            'tax_id': clinic.tax_id if clinic else '',
        },
        'patient': {
            'name': f"{patient.first_name or ''} {patient.last_name or ''}".strip() if patient else '',
            'id': str(patient.id) if patient else '',
        },
        'doctor': {
            'name': f"{doctor.first_name or ''} {doctor.last_name or ''}".strip() if doctor else '',
            'crm': getattr(doctor, 'crm', '') or '',
        },
        'medications': [
            {
                'name': prescription.medication_name,
                'dosage': prescription.dosage,
                'frequency': prescription.frequency,
                'duration': prescription.duration or '',
                'notes': prescription.instructions or '',
            }
        ]
    }
    
    return prescription_data


@router.post("/consultations/{appointment_id}/generate-pdf")
async def generate_consultation_pdf(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate PDF report for a consultation/appointment
    
    Includes:
    - Patient information
    - Appointment details
    - SOAP notes (Subjective, Objective, Assessment, Plan)
    - Diagnoses
    - Prescriptions
    - Exam requests
    - Doctor signature
    """
    try:
        # Fetch consultation data
        consultation_data = await _get_consultation_data(appointment_id, current_user, db)
        
        # Generate PDF
        pdf_bytes = pdf_generator.generate_consultation_report(consultation_data)
        
        # Return as streaming response
        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="consulta_{appointment_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating PDF: {str(e)}"
        )


@router.get("/prescriptions/{prescription_id}/pdf")
async def generate_prescription_pdf_endpoint(
    prescription_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate and download prescription PDF
    
    Returns a formatted prescription document with:
    - Patient information
    - Medication details (name, dosage, frequency, duration)
    - Doctor signature
    """
    try:
        # Fetch prescription data
        prescription_data = await _get_prescription_data(prescription_id, current_user, db)
        
        # Generate PDF using existing function
        pdf_bytes = pdf_generator.generate_prescription(prescription_data)
        
        # Return as streaming response
        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="receita_{prescription_id}_{datetime.now().strftime("%Y%m%d")}.pdf"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating prescription PDF: {str(e)}"
        )


@router.post("/certificates/generate")
async def generate_medical_certificate(
    certificate_data: dict = Body(...),
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate medical certificate PDF
    
    Request body should contain:
    - patient_id: Patient ID
    - justification: Certificate justification text
    - validity_days: Number of days the certificate is valid
    
    Optional:
    - clinic_id: Clinic ID (defaults to current user's clinic)
    """
    try:
        # Get patient
        patient_id = certificate_data.get('patient_id')
        if not patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patient_id is required"
            )
        
        patient_query = select(Patient).filter(
            Patient.id == patient_id,
            Patient.clinic_id == current_user.clinic_id
        )
        result = await db.execute(patient_query)
        patient = result.scalar_one_or_none()
        
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found"
            )
        
        # Get clinic
        clinic_query = select(Clinic).filter(Clinic.id == current_user.clinic_id)
        clinic_result = await db.execute(clinic_query)
        clinic = clinic_result.scalar_one_or_none()
        
        # Build certificate data
        cert_data = {
            'clinic': {
                'name': clinic.name if clinic else 'Prontivus Clinic',
                'address': clinic.address if clinic else '',
                'phone': clinic.phone if clinic else '',
                'email': clinic.email if clinic else '',
                'tax_id': clinic.tax_id if clinic else '',
            },
            'patient': {
                'name': f"{patient.first_name} {patient.last_name}".strip(),
                'document': patient.cpf or '',
            },
            'doctor': {
                'name': f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
                'crm': getattr(current_user, 'crm', '') or '',
            },
            'justification': certificate_data.get('justification', ''),
            'validity_days': certificate_data.get('validity_days', 0),
        }
        
        # Generate PDF
        pdf_bytes = pdf_generator.generate_medical_certificate(cert_data)
        
        # Return as streaming response
        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="atestado_{datetime.now().strftime("%Y%m%d")}.pdf"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating certificate PDF: {str(e)}"
        )


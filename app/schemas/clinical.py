"""
Clinical Pydantic schemas for request/response validation
"""
import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.clinical import UrgencyLevel, DiagnosisType


# ==================== Clinical Record Schemas ====================

class ClinicalRecordBase(BaseModel):
    subjective: Optional[str] = Field(None, description="Patient's complaints and symptoms")
    objective: Optional[str] = Field(None, description="Physical exam findings, vital signs")
    assessment: Optional[str] = Field(None, description="Diagnosis or clinical impression")
    plan: Optional[str] = Field(None, description="Legacy treatment plan")
    plan_soap: Optional[str] = Field(None, description="SOAP Plan section")


class ClinicalRecordCreate(ClinicalRecordBase):
    appointment_id: int


class ClinicalRecordUpdate(ClinicalRecordBase):
    pass


class ClinicalRecordResponse(ClinicalRecordBase):
    id: int
    appointment_id: int
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime]
    
    class Config:
        from_attributes = True


# ==================== Prescription Schemas ====================

class PrescriptionBase(BaseModel):
    medication_name: str = Field(..., max_length=200, description="Medication name")
    dosage: str = Field(..., max_length=100, description="Dosage (e.g., 500mg, 10ml)")
    frequency: str = Field(..., max_length=100, description="Frequency (e.g., 3x ao dia)")
    duration: Optional[str] = Field(None, max_length=100, description="Duration (e.g., 7 dias)")
    instructions: Optional[str] = Field(None, description="Special instructions")


class PrescriptionCreate(PrescriptionBase):
    clinical_record_id: int


class PrescriptionUpdate(BaseModel):
    medication_name: Optional[str] = Field(None, max_length=200)
    dosage: Optional[str] = Field(None, max_length=100)
    frequency: Optional[str] = Field(None, max_length=100)
    duration: Optional[str] = Field(None, max_length=100)
    instructions: Optional[str] = None
    is_active: Optional[bool] = None


class PrescriptionResponse(PrescriptionBase):
    id: int
    clinical_record_id: int
    issued_date: datetime.datetime
    is_active: bool
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime]
    
    class Config:
        from_attributes = True


# ==================== Exam Request Schemas ====================

class ExamRequestBase(BaseModel):
    exam_type: str = Field(..., max_length=200, description="Type of exam (e.g., Hemograma, Raio-X)")
    description: Optional[str] = Field(None, description="Additional details")
    reason: Optional[str] = Field(None, description="Clinical indication")
    urgency: UrgencyLevel = Field(default=UrgencyLevel.ROUTINE, description="Urgency level")


class ExamRequestCreate(ExamRequestBase):
    clinical_record_id: int


class ExamRequestUpdate(BaseModel):
    exam_type: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    reason: Optional[str] = None
    urgency: Optional[UrgencyLevel] = None
    completed: Optional[bool] = None
    completed_date: Optional[datetime.datetime] = None


class ExamRequestResponse(ExamRequestBase):
    id: int
    clinical_record_id: int
    requested_date: datetime.datetime
    completed: bool
    completed_date: Optional[datetime.datetime]
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime]
    
    class Config:
        from_attributes = True


# ==================== Complete Clinical Record with Relations ====================

class ClinicalRecordDetailResponse(ClinicalRecordResponse):
    """Clinical record with all prescriptions and exam requests"""
    prescriptions: List[PrescriptionResponse] = []
    exam_requests: List[ExamRequestResponse] = []
    # filled by join on demand
    diagnoses: List["DiagnosisResponse"] = []
    
    class Config:
        from_attributes = True


# ==================== Patient Clinical History ====================

class PatientClinicalHistoryResponse(BaseModel):
    """Patient's complete clinical history"""
    appointment_id: int
    appointment_date: datetime.datetime
    doctor_name: str
    appointment_type: Optional[str]
    clinical_record: Optional[ClinicalRecordDetailResponse]
    
    class Config:
        from_attributes = True
# ==================== Version History ====================

class ClinicalRecordVersionResponse(BaseModel):
    id: int
    clinical_record_id: int
    author_user_id: int | None
    is_autosave: bool
    snapshot: dict
    created_at: datetime.datetime

    class Config:
        from_attributes = True



# ==================== Diagnosis Schemas ====================

class DiagnosisBase(BaseModel):
    cid_code: str = Field(..., max_length=16)
    description: Optional[str] = None
    type: DiagnosisType = DiagnosisType.PRIMARY


class DiagnosisCreate(DiagnosisBase):
    clinical_record_id: int


class DiagnosisUpdate(BaseModel):
    cid_code: Optional[str] = Field(None, max_length=16)
    description: Optional[str] = None
    type: Optional[DiagnosisType] = None


class DiagnosisResponse(DiagnosisBase):
    id: int
    clinical_record_id: int
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime]
    
    class Config:
        from_attributes = True


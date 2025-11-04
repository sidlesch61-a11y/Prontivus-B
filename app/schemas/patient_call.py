from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class PatientCallResponse(BaseModel):
    id: int
    appointment_id: int
    patient_id: int
    doctor_id: int
    clinic_id: int
    status: str
    called_at: datetime
    answered_at: Optional[datetime] = None
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    room_number: Optional[str] = None

    class Config:
        from_attributes = True


class PatientCallCreate(BaseModel):
    appointment_id: int


class PatientCallUpdate(BaseModel):
    status: Optional[str] = None
    answered_at: Optional[datetime] = None


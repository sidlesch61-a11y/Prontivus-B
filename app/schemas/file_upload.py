from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class FileUploadResponse(BaseModel):
    id: int
    patient_id: int
    appointment_id: Optional[int]
    filename: str
    filetype: str
    upload_date: datetime
    uploaded_by: int
    exam_type: Optional[str]
    exam_date: Optional[datetime]
    laboratory: Optional[str]
    observations: Optional[str]

    class Config:
        from_attributes = True



from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models import UserRole


class SystemLogBase(BaseModel):
    level: str
    message: str
    source: str
    details: Optional[str] = None
    user_id: Optional[int] = None
    clinic_id: Optional[int] = None


class SystemLogCreate(SystemLogBase):
    pass


class SystemLogUpdate(BaseModel):
    level: Optional[str] = None
    message: Optional[str] = None
    source: Optional[str] = None
    details: Optional[str] = None


class SystemLogResponse(SystemLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True



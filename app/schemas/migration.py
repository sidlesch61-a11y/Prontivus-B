from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class MigrationJobCreate(BaseModel):
    type: str  # patients|appointments|clinical|financial
    input_format: str  # csv|json
    source_name: Optional[str] = None
    params: Optional[dict] = None


class MigrationJobResponse(BaseModel):
    id: int
    clinic_id: int
    created_by: int
    type: str
    status: str
    input_format: str
    source_name: Optional[str]
    params: Optional[dict]
    stats: Optional[dict]
    errors: Optional[dict]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True



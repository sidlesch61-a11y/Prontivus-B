"""
Message schemas for API validation
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.message import MessageStatus


class MessageBase(BaseModel):
    content: str = Field(default="", min_length=0)  # Allow empty content if attachments are present
    attachments: Optional[List[Dict[str, Any]]] = None
    medical_context: Optional[Dict[str, Any]] = None


class MessageCreate(MessageBase):
    # thread_id comes from the URL path, not the request body
    pass


class MessageResponse(MessageBase):
    id: int
    thread_id: int
    sender_id: int
    sender_type: str
    status: str  # Changed from MessageStatus to str since we're storing as VARCHAR
    created_at: datetime
    read_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class MessageThreadBase(BaseModel):
    provider_id: int
    topic: Optional[str] = None
    is_urgent: bool = False


class MessageThreadCreate(MessageThreadBase):
    pass


class MessageThreadResponse(BaseModel):
    id: int
    patient_id: int
    provider_id: int
    provider_name: str
    provider_specialty: Optional[str] = None
    topic: Optional[str] = None
    is_urgent: bool
    is_archived: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    last_message: Optional[str] = None
    unread_count: int = 0
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class MessageThreadDetailResponse(MessageThreadResponse):
    messages: List[MessageResponse] = []


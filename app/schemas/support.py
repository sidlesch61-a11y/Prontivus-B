"""
Support Ticket and Help Article Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.support import TicketStatus, TicketPriority


class SupportTicketCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    priority: TicketPriority = TicketPriority.MEDIUM


class SupportTicketUpdate(BaseModel):
    subject: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None


class SupportTicketResponse(BaseModel):
    id: int
    patient_id: int
    clinic_id: int
    subject: str
    description: str
    status: str
    priority: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    is_active: bool

    class Config:
        from_attributes = True


class HelpArticleCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1, max_length=100)
    tags: Optional[List[str]] = []


class HelpArticleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = Field(None, min_length=1)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class HelpArticleResponse(BaseModel):
    id: int
    clinic_id: Optional[int] = None
    title: str
    content: str
    category: str
    tags: List[str] = []
    views: int
    helpful_count: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


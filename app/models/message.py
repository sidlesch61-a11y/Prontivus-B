"""
Message models for patient-provider communication
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum
import datetime


class MessageStatus(str, enum.Enum):
    """Message status enumeration"""
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class MessageThread(Base):
    """
    Message Thread Model
    Represents a conversation between a patient and a provider (doctor/staff)
    """
    __tablename__ = "message_threads"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Participants
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # doctor or staff
    
    # Thread metadata
    topic = Column(String(200), nullable=True)  # e.g., "Prescription Renewal", "Test Results"
    is_urgent = Column(Boolean, default=False, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.datetime.now)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    patient = relationship("Patient", back_populates="message_threads")
    provider = relationship("User", foreign_keys=[provider_id])
    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan", order_by="Message.created_at")
    
    # Foreign Keys
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True)
    clinic = relationship("Clinic")


class Message(Base):
    """
    Message Model
    Individual messages within a thread
    """
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Thread relationship
    thread_id = Column(Integer, ForeignKey("message_threads.id"), nullable=False, index=True)
    
    # Sender information
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Can be patient's user ID or provider's user ID
    sender_type = Column(String(20), nullable=False)  # "patient" or "provider" or "system"
    
    # Message content
    content = Column(Text, nullable=False)
    status = Column(SQLEnum(MessageStatus, native_enum=False), default=MessageStatus.SENT.value, nullable=False)
    
    # Attachments and metadata
    attachments = Column(JSON, nullable=True)  # Array of attachment objects: {name, type, url, size}
    medical_context = Column(JSON, nullable=True)  # {type: "prescription"|"test_result"|"appointment", reference_id: ...}
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    thread = relationship("MessageThread", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])


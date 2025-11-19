"""
TISS Template Model
Stores XML templates for TISS document generation
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, Enum as SQLEnum, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models import BaseModel
import enum


class TissTemplateCategory(str, enum.Enum):
    """TISS Template categories"""
    CONSULTATION = "consultation"
    PROCEDURE = "procedure"
    EXAM = "exam"
    EMERGENCY = "emergency"
    CUSTOM = "custom"


class TissTemplate(BaseModel):
    """
    TISS Template Model
    Stores reusable XML templates for TISS document generation
    """
    __tablename__ = "tiss_templates"
    
    # Basic Information
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, default=TissTemplateCategory.CUSTOM.value)
    
    # Template Content
    xml_template = Column(Text, nullable=False)  # XML template with variables like {{VARIABLE_NAME}}
    variables = Column(JSON, nullable=True, default=list)  # List of variable names found in template
    
    # Status
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Foreign Keys
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    clinic = relationship("Clinic", backref="tiss_templates")
    created_by = relationship("User", foreign_keys=[created_by_id])
    
    def __repr__(self):
        return f"<TissTemplate(id={self.id}, name='{self.name}', category='{self.category}')>"
    
    def extract_variables(self) -> list[str]:
        """Extract variable names from XML template (e.g., {{VARIABLE_NAME}})"""
        import re
        pattern = r'\{\{(\w+)\}\}'
        variables = re.findall(pattern, self.xml_template)
        return list(set(variables))  # Return unique variables


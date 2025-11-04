import enum
from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from app.models import BaseModel

# Models
class Procedure(Base):
    """Represents a medical procedure that can be performed"""
    __tablename__ = "procedures"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    duration = Column(Integer, nullable=False, default=30)  # Duration in minutes
    cost = Column(Numeric(10, 2), nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    clinic = relationship("Clinic", back_populates="procedures")
    procedure_products = relationship("ProcedureProduct", back_populates="procedure", cascade="all, delete-orphan")
    invoice_lines = relationship("InvoiceLine", back_populates="procedure")

    def __repr__(self):
        return f"<Procedure(id={self.id}, name='{self.name}', cost={self.cost})>"

class ProcedureProduct(Base):
    """Represents products required for a procedure (technical sheet)"""
    __tablename__ = "procedure_products"

    id = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity_required = Column(Numeric(10, 2), nullable=False, default=1)
    notes = Column(Text, nullable=True)  # Optional notes about product usage
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    procedure = relationship("Procedure", back_populates="procedure_products")
    product = relationship("Product", back_populates="procedure_products")

    def __repr__(self):
        return f"<ProcedureProduct(id={self.id}, procedure_id={self.procedure_id}, product_id={self.product_id}, quantity={self.quantity_required})>"

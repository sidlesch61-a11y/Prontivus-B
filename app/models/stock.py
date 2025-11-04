"""
Stock/Inventory Management Models
Handles products, stock movements, and inventory tracking
"""

import enum
from sqlalchemy import Column, Integer, String, Text, Numeric, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from app.models import BaseModel

# Enums
class ProductCategory(str, enum.Enum):
    MEDICATION = "medication"
    MEDICAL_SUPPLY = "medical_supply"
    EQUIPMENT = "equipment"
    CONSUMABLE = "consumable"
    INSTRUMENT = "instrument"
    OTHER = "other"

class StockMovementType(str, enum.Enum):
    IN = "in"           # Stock increase (purchase, return, etc.)
    OUT = "out"         # Stock decrease (usage, sale, etc.)
    ADJUSTMENT = "adjustment"  # Manual adjustment
    TRANSFER = "transfer"      # Transfer between locations
    EXPIRED = "expired"        # Stock removed due to expiration
    DAMAGED = "damaged"        # Stock removed due to damage

class StockMovementReason(str, enum.Enum):
    PURCHASE = "purchase"
    SALE = "sale"
    USAGE = "usage"
    RETURN = "return"
    ADJUSTMENT = "adjustment"
    TRANSFER = "transfer"
    EXPIRED = "expired"
    DAMAGED = "damaged"
    THEFT = "theft"
    DONATION = "donation"
    OTHER = "other"

# Models
class Product(Base):
    """Products/Items in inventory"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(SQLEnum(ProductCategory), nullable=False, default=ProductCategory.OTHER)
    supplier = Column(String(200), nullable=True)
    min_stock = Column(Integer, nullable=False, default=0)
    current_stock = Column(Integer, nullable=False, default=0)
    unit_price = Column(Numeric(10, 2), nullable=True)
    unit_of_measure = Column(String(50), nullable=True, default="unidade")  # unidade, caixa, frasco, etc.
    barcode = Column(String(100), nullable=True, unique=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    stock_movements = relationship("StockMovement", back_populates="product", cascade="all, delete-orphan")
    clinic = relationship("Clinic", back_populates="products")
    procedure_products = relationship("ProcedureProduct", back_populates="product", cascade="all, delete-orphan")

class StockMovement(Base):
    """Stock movement transactions"""
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    type = Column(SQLEnum(StockMovementType), nullable=False)
    quantity = Column(Integer, nullable=False)  # Positive for IN, negative for OUT
    reason = Column(SQLEnum(StockMovementReason), nullable=False)
    description = Column(Text, nullable=True)
    related_id = Column(Integer, nullable=True)  # FK to InvoiceLine, Procedure, etc.
    related_type = Column(String(50), nullable=True)  # "invoice_line", "procedure", etc.
    unit_cost = Column(Numeric(10, 2), nullable=True)  # Cost per unit for this movement
    total_cost = Column(Numeric(10, 2), nullable=True)  # Total cost for this movement
    reference_number = Column(String(100), nullable=True)  # Invoice number, PO number, etc.
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    product = relationship("Product", back_populates="stock_movements")
    clinic = relationship("Clinic", back_populates="stock_movements")
    creator = relationship("User", foreign_keys=[created_by])

class StockAlert(Base):
    """Stock alerts and notifications"""
    __tablename__ = "stock_alerts"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    alert_type = Column(String(50), nullable=False)  # "low_stock", "expired", "near_expiry"
    message = Column(Text, nullable=False)
    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    product = relationship("Product")
    clinic = relationship("Clinic", back_populates="stock_alerts")
    resolver = relationship("User", foreign_keys=[resolved_by])

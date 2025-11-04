"""
Stock/Inventory Management Schemas
Pydantic schemas for inventory management
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models.stock import ProductCategory, StockMovementType, StockMovementReason

# ==================== Product Schemas ====================

class ProductBase(BaseModel):
    name: str = Field(..., max_length=200, description="Product name")
    description: Optional[str] = Field(None, description="Product description")
    category: ProductCategory = Field(..., description="Product category")
    supplier: Optional[str] = Field(None, max_length=200, description="Supplier name")
    min_stock: int = Field(..., ge=0, description="Minimum stock level")
    current_stock: int = Field(0, ge=0, description="Current stock quantity")
    unit_price: Optional[float] = Field(None, ge=0, description="Unit price")
    unit_of_measure: str = Field("unidade", max_length=50, description="Unit of measure")
    barcode: Optional[str] = Field(None, max_length=100, description="Product barcode")
    is_active: bool = Field(True, description="Whether product is active")

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    category: Optional[ProductCategory] = None
    supplier: Optional[str] = Field(None, max_length=200)
    min_stock: Optional[int] = Field(None, ge=0)
    unit_price: Optional[float] = Field(None, ge=0)
    unit_of_measure: Optional[str] = Field(None, max_length=50)
    barcode: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None

class ProductResponse(ProductBase):
    id: int
    clinic_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    stock_status: Optional[str] = Field(None, description="Stock status: 'low', 'normal', 'out_of_stock'")

    class Config:
        from_attributes = True

class ProductWithMovements(ProductResponse):
    recent_movements: List["StockMovementResponse"] = []

# ==================== Stock Movement Schemas ====================

class StockMovementBase(BaseModel):
    type: StockMovementType = Field(..., description="Type of movement")
    quantity: int = Field(..., description="Quantity moved (positive for IN, negative for OUT)")
    reason: StockMovementReason = Field(..., description="Reason for movement")
    description: Optional[str] = Field(None, description="Additional description")
    related_id: Optional[int] = Field(None, description="Related record ID")
    related_type: Optional[str] = Field(None, max_length=50, description="Type of related record")
    unit_cost: Optional[float] = Field(None, ge=0, description="Cost per unit")
    total_cost: Optional[float] = Field(None, ge=0, description="Total cost")
    reference_number: Optional[str] = Field(None, max_length=100, description="Reference number")

class StockMovementCreate(StockMovementBase):
    product_id: int = Field(..., description="Product ID")

class StockMovementUpdate(BaseModel):
    type: Optional[StockMovementType] = None
    quantity: Optional[int] = None
    reason: Optional[StockMovementReason] = None
    description: Optional[str] = None
    related_id: Optional[int] = None
    related_type: Optional[str] = Field(None, max_length=50)
    unit_cost: Optional[float] = Field(None, ge=0)
    total_cost: Optional[float] = Field(None, ge=0)
    reference_number: Optional[str] = Field(None, max_length=100)

class StockMovementResponse(StockMovementBase):
    id: int
    product_id: int
    clinic_id: int
    created_by: Optional[int] = None
    timestamp: datetime
    product_name: Optional[str] = None
    creator_name: Optional[str] = None

    class Config:
        from_attributes = True

# ==================== Stock Adjustment Schemas ====================

class StockAdjustmentCreate(BaseModel):
    product_id: int = Field(..., description="Product ID to adjust")
    new_quantity: int = Field(..., ge=0, description="New stock quantity")
    reason: StockMovementReason = Field(..., description="Reason for adjustment")
    description: Optional[str] = Field(None, description="Additional description")
    reference_number: Optional[str] = Field(None, max_length=100, description="Reference number")

class StockAdjustmentResponse(BaseModel):
    product_id: int
    old_quantity: int
    new_quantity: int
    difference: int
    movement_id: int
    message: str

# ==================== Stock Alert Schemas ====================

class StockAlertBase(BaseModel):
    alert_type: str = Field(..., max_length=50, description="Type of alert")
    message: str = Field(..., description="Alert message")
    is_resolved: bool = Field(False, description="Whether alert is resolved")

class StockAlertCreate(StockAlertBase):
    product_id: int = Field(..., description="Product ID")

class StockAlertResponse(StockAlertBase):
    id: int
    product_id: int
    clinic_id: int
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None
    created_at: datetime
    product_name: Optional[str] = None
    resolver_name: Optional[str] = None

    class Config:
        from_attributes = True

# ==================== Dashboard/Summary Schemas ====================

class StockSummary(BaseModel):
    total_products: int
    low_stock_products: int
    out_of_stock_products: int
    total_value: float
    recent_movements: int
    pending_alerts: int

class LowStockProduct(BaseModel):
    id: int
    name: str
    current_stock: int
    min_stock: int
    category: ProductCategory
    days_until_out: Optional[int] = None

class StockMovementSummary(BaseModel):
    date: str
    movements_in: int
    movements_out: int
    total_products_affected: int

# Update forward references
ProductWithMovements.model_rebuild()

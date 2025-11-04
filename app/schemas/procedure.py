from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models.procedure import Procedure, ProcedureProduct

# Procedure Schemas
class ProcedureBase(BaseModel):
    name: str = Field(..., max_length=200, description="Name of the procedure")
    description: Optional[str] = Field(None, description="Detailed description of the procedure")
    duration: int = Field(30, ge=1, le=480, description="Duration in minutes (1-480)")
    cost: float = Field(0, ge=0, description="Cost of the procedure")
    is_active: bool = Field(True, description="Whether the procedure is active")

class ProcedureCreate(ProcedureBase):
    pass

class ProcedureUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    duration: Optional[int] = Field(None, ge=1, le=480)
    cost: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None

class ProcedureResponse(ProcedureBase):
    id: int
    clinic_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    procedure_products: List["ProcedureProductResponse"] = []

    class Config:
        from_attributes = True

# Procedure Product Schemas
class ProcedureProductBase(BaseModel):
    product_id: int = Field(..., description="ID of the product required")
    quantity_required: float = Field(..., gt=0, description="Quantity of product required")
    notes: Optional[str] = Field(None, description="Optional notes about product usage")

class ProcedureProductCreate(ProcedureProductBase):
    pass

class ProcedureProductUpdate(BaseModel):
    quantity_required: Optional[float] = Field(None, gt=0)
    notes: Optional[str] = None

class ProcedureProductResponse(ProcedureProductBase):
    id: int
    procedure_id: int
    created_at: datetime
    product_name: Optional[str] = None  # Will be populated from relationship
    product_unit_of_measure: Optional[str] = None  # Will be populated from relationship

    class Config:
        from_attributes = True

# Combined schemas for creating procedures with products
class ProcedureWithProductsCreate(BaseModel):
    procedure: ProcedureCreate
    products: List[ProcedureProductCreate] = Field(default_factory=list, description="List of products required for this procedure")

class ProcedureWithProductsResponse(ProcedureResponse):
    procedure_products: List[ProcedureProductResponse] = []

# Update the forward reference
ProcedureResponse.model_rebuild()

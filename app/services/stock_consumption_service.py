"""
Stock Consumption Service
Handles automatic stock consumption when procedures are billed
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from decimal import Decimal

from app.models import Procedure, ProcedureProduct, Product, StockMovement, StockMovementType, StockMovementReason
from app.schemas.stock import StockMovementCreate


async def consume_stock_for_procedure(
    procedure_id: int,
    quantity: Decimal,
    clinic_id: int,
    created_by: int,
    db: AsyncSession,
    reference_number: str = None
) -> List[StockMovement]:
    """
    Consume stock for a procedure based on its technical sheet
    
    Args:
        procedure_id: ID of the procedure being billed
        quantity: Quantity of the procedure being performed
        clinic_id: ID of the clinic
        created_by: ID of the user creating the movement
        db: Database session
        reference_number: Optional reference number (e.g., invoice number)
    
    Returns:
        List of created stock movements
    """
    # Get procedure with its products
    procedure_query = select(Procedure).options(
        selectinload(Procedure.procedure_products).selectinload(ProcedureProduct.product)
    ).filter(
        Procedure.id == procedure_id,
        Procedure.clinic_id == clinic_id
    )
    procedure_result = await db.execute(procedure_query)
    procedure = procedure_result.unique().scalar_one_or_none()
    
    if not procedure:
        raise ValueError(f"Procedure {procedure_id} not found")
    
    if not procedure.procedure_products:
        # No products required for this procedure
        return []
    
    created_movements = []
    
    for procedure_product in procedure.procedure_products:
        # Calculate total quantity needed
        total_quantity_needed = float(procedure_product.quantity_required) * float(quantity)
        
        # Check if enough stock is available
        product = procedure_product.product
        if product.current_stock < total_quantity_needed:
            raise ValueError(
                f"Insufficient stock for product '{product.name}'. "
                f"Required: {total_quantity_needed}, Available: {product.current_stock}"
            )
        
        # Create stock movement
        movement_data = StockMovementCreate(
            product_id=product.id,
            type=StockMovementType.OUT,
            quantity=total_quantity_needed,
            reason=StockMovementReason.USAGE,
            description=f"Procedure: {procedure.name}",
            related_id=procedure_id,
            related_type="procedure",
            reference_number=reference_number
        )
        
        # Update product stock
        product.current_stock -= total_quantity_needed
        
        # Create stock movement record
        db_movement = StockMovement(
            clinic_id=clinic_id,
            created_by=created_by,
            **movement_data.model_dump()
        )
        db.add(db_movement)
        created_movements.append(db_movement)
    
    return created_movements


async def check_stock_availability_for_procedure(
    procedure_id: int,
    quantity: Decimal,
    clinic_id: int,
    db: AsyncSession
) -> dict:
    """
    Check if there's enough stock available for a procedure
    
    Args:
        procedure_id: ID of the procedure
        quantity: Quantity of the procedure
        clinic_id: ID of the clinic
        db: Database session
    
    Returns:
        Dictionary with availability status and details
    """
    # Get procedure with its products
    procedure_query = select(Procedure).options(
        selectinload(Procedure.procedure_products).selectinload(ProcedureProduct.product)
    ).filter(
        Procedure.id == procedure_id,
        Procedure.clinic_id == clinic_id
    )
    procedure_result = await db.execute(procedure_query)
    procedure = procedure_result.unique().scalar_one_or_none()
    
    if not procedure:
        return {
            "available": False,
            "error": f"Procedure {procedure_id} not found"
        }
    
    if not procedure.procedure_products:
        return {
            "available": True,
            "message": "No products required for this procedure"
        }
    
    insufficient_products = []
    
    for procedure_product in procedure.procedure_products:
        total_quantity_needed = float(procedure_product.quantity_required) * float(quantity)
        product = procedure_product.product
        
        if product.current_stock < total_quantity_needed:
            insufficient_products.append({
                "product_id": product.id,
                "product_name": product.name,
                "required": total_quantity_needed,
                "available": product.current_stock,
                "shortage": total_quantity_needed - product.current_stock
            })
    
    if insufficient_products:
        return {
            "available": False,
            "insufficient_products": insufficient_products
        }
    
    return {
        "available": True,
        "message": "All products available"
    }

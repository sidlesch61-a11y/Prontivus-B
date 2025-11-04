"""
Stock/Inventory Management API Endpoints
Handles product management, stock movements, and inventory tracking
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional
from datetime import datetime, timedelta

from app.core.auth import get_current_user
from database import get_async_session
from app.models import (
    User, Product, StockMovement, StockAlert, ProductCategory, 
    StockMovementType, StockMovementReason, UserRole
)
from app.schemas.stock import (
    ProductCreate, ProductUpdate, ProductResponse, ProductWithMovements,
    StockMovementCreate, StockMovementUpdate, StockMovementResponse,
    StockAdjustmentCreate, StockAdjustmentResponse,
    StockAlertResponse, StockSummary, LowStockProduct, StockMovementSummary
)

router = APIRouter(tags=["Stock/Inventory"])

# ==================== Products ====================

@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_in: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new product
    Requires staff role (admin or secretary)
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can create products"
        )
    # Check if barcode already exists
    if product_in.barcode:
        existing_product = await db.execute(
            select(Product).filter(
                Product.barcode == product_in.barcode,
                Product.clinic_id == current_user.clinic_id
            )
        )
        if existing_product.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product with this barcode already exists"
            )

    db_product = Product(
        clinic_id=current_user.clinic_id,
        **product_in.model_dump()
    )
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    
    # Add stock status
    product_data = db_product.__dict__.copy()
    product_data['stock_status'] = _get_stock_status(db_product.current_stock, db_product.min_stock)
    product_response = ProductResponse.model_validate(product_data)
    
    return product_response

@router.get("/products", response_model=List[ProductResponse])
async def get_products(
    category: Optional[ProductCategory] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    low_stock: Optional[bool] = Query(None, description="Show only low stock products"),
    search: Optional[str] = Query(None, description="Search by name or description"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get list of products
    """
    query = select(Product).filter(Product.clinic_id == current_user.clinic_id)
    
    if category:
        query = query.filter(Product.category == category)
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    if low_stock:
        query = query.filter(Product.current_stock <= Product.min_stock)
    if search:
        query = query.filter(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.description.ilike(f"%{search}%"),
                Product.supplier.ilike(f"%{search}%")
            )
        )
    
    query = query.order_by(Product.name)
    result = await db.execute(query)
    products = result.scalars().all()
    
    # Add stock status to each product
    product_responses = []
    for product in products:
        product_data = product.__dict__.copy()
        product_data['stock_status'] = _get_stock_status(product.current_stock, product.min_stock)
        product_response = ProductResponse.model_validate(product_data)
        product_responses.append(product_response)
    
    return product_responses

@router.get("/products/{product_id}", response_model=ProductWithMovements)
async def get_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get a specific product with recent movements
    """
    product_query = select(Product).filter(
        Product.id == product_id,
        Product.clinic_id == current_user.clinic_id
    )
    product_result = await db.execute(product_query)
    product = product_result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Get recent movements
    movements_query = select(StockMovement).filter(
        StockMovement.product_id == product_id
    ).order_by(desc(StockMovement.timestamp)).limit(10)
    
    movements_result = await db.execute(movements_query)
    movements = movements_result.scalars().all()
    
    # Build response
    product_response = ProductWithMovements.model_validate(product)
    product_response.stock_status = _get_stock_status(product.current_stock, product.min_stock)
    product_response.recent_movements = [
        StockMovementResponse.model_validate(movement) for movement in movements
    ]
    
    return product_response

@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    product_in: ProductUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update a product
    Requires staff role
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can update products"
        )
    product_query = select(Product).filter(
        Product.id == product_id,
        Product.clinic_id == current_user.clinic_id
    )
    product_result = await db.execute(product_query)
    product = product_result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check barcode uniqueness if being updated
    if product_in.barcode and product_in.barcode != product.barcode:
        existing_product = await db.execute(
            select(Product).filter(
                Product.barcode == product_in.barcode,
                Product.clinic_id == current_user.clinic_id,
                Product.id != product_id
            )
        )
        if existing_product.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product with this barcode already exists"
            )
    
    # Update product
    update_data = product_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    
    await db.commit()
    await db.refresh(product)
    
    product_data = product.__dict__.copy()
    product_data['stock_status'] = _get_stock_status(product.current_stock, product.min_stock)
    product_response = ProductResponse.model_validate(product_data)
    
    return product_response

@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Delete a product (soft delete by setting is_active to False)
    Requires staff role
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can delete products"
        )
    product_query = select(Product).filter(
        Product.id == product_id,
        Product.clinic_id == current_user.clinic_id
    )
    product_result = await db.execute(product_query)
    product = product_result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Soft delete
    product.is_active = False
    await db.commit()
    
    return {"message": "Product deleted successfully"}

# ==================== Stock Movements ====================

@router.post("/stock-movements", response_model=StockMovementResponse, status_code=status.HTTP_201_CREATED)
async def create_stock_movement(
    movement_in: StockMovementCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new stock movement
    Requires staff role
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can create stock movements"
        )
    # Verify product exists and belongs to clinic
    product_query = select(Product).filter(
        Product.id == movement_in.product_id,
        Product.clinic_id == current_user.clinic_id
    )
    product_result = await db.execute(product_query)
    product = product_result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Create movement
    db_movement = StockMovement(
        clinic_id=current_user.clinic_id,
        created_by=current_user.id,
        **movement_in.model_dump()
    )
    db.add(db_movement)
    
    # Update product stock
    if movement_in.type == StockMovementType.IN:
        product.current_stock += movement_in.quantity
    elif movement_in.type == StockMovementType.OUT:
        if product.current_stock < movement_in.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock"
            )
        product.current_stock -= movement_in.quantity
    elif movement_in.type == StockMovementType.ADJUSTMENT:
        product.current_stock = movement_in.quantity
    
    await db.commit()
    await db.refresh(db_movement)
    
    return StockMovementResponse.model_validate(db_movement)

@router.post("/stock-movements/adjustment", response_model=StockAdjustmentResponse)
async def adjust_stock(
    adjustment_in: StockAdjustmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Manually adjust stock for a product
    Requires staff role
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can adjust stock"
        )
    # Get product
    product_query = select(Product).filter(
        Product.id == adjustment_in.product_id,
        Product.clinic_id == current_user.clinic_id
    )
    product_result = await db.execute(product_query)
    product = product_result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    old_quantity = product.current_stock
    difference = adjustment_in.new_quantity - old_quantity
    
    # Create adjustment movement
    movement = StockMovement(
        product_id=adjustment_in.product_id,
        clinic_id=current_user.clinic_id,
        created_by=current_user.id,
        type=StockMovementType.ADJUSTMENT,
        quantity=difference,
        reason=adjustment_in.reason,
        description=adjustment_in.description,
        reference_number=adjustment_in.reference_number
    )
    db.add(movement)
    
    # Update product stock
    product.current_stock = adjustment_in.new_quantity
    
    await db.commit()
    await db.refresh(movement)
    
    return StockAdjustmentResponse(
        product_id=product.id,
        old_quantity=old_quantity,
        new_quantity=adjustment_in.new_quantity,
        difference=difference,
        movement_id=movement.id,
        message=f"Stock adjusted from {old_quantity} to {adjustment_in.new_quantity}"
    )

@router.get("/stock-movements", response_model=List[StockMovementResponse])
async def get_stock_movements(
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    movement_type: Optional[StockMovementType] = Query(None, description="Filter by movement type"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    limit: int = Query(100, le=1000, description="Limit number of results"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get stock movements with optional filters
    """
    query = select(StockMovement).filter(
        StockMovement.clinic_id == current_user.clinic_id
    )
    
    if product_id:
        query = query.filter(StockMovement.product_id == product_id)
    if movement_type:
        query = query.filter(StockMovement.type == movement_type)
    if start_date:
        query = query.filter(StockMovement.timestamp >= start_date)
    if end_date:
        query = query.filter(StockMovement.timestamp <= end_date)
    
    query = query.order_by(desc(StockMovement.timestamp)).limit(limit)
    result = await db.execute(query)
    movements = result.scalars().all()
    
    return [StockMovementResponse.model_validate(movement) for movement in movements]

@router.get("/stock-movements/low-stock", response_model=List[LowStockProduct])
async def get_low_stock_products(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get products that are below their minimum stock level
    """
    query = select(Product).filter(
        Product.clinic_id == current_user.clinic_id,
        Product.is_active == True,
        Product.current_stock <= Product.min_stock
    ).order_by(Product.current_stock.asc())
    
    result = await db.execute(query)
    products = result.scalars().all()
    
    low_stock_products = []
    for product in products:
        # Calculate days until out of stock (rough estimate)
        days_until_out = None
        if product.current_stock > 0:
            # This is a simplified calculation - in reality you'd need usage history
            days_until_out = max(1, product.current_stock)
        
        low_stock_products.append(LowStockProduct(
            id=product.id,
            name=product.name,
            current_stock=product.current_stock,
            min_stock=product.min_stock,
            category=product.category,
            days_until_out=days_until_out
        ))
    
    return low_stock_products

# ==================== Dashboard/Summary ====================

@router.get("/dashboard/summary", response_model=StockSummary)
async def get_stock_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get stock dashboard summary
    """
    # Total products
    total_products_query = select(func.count(Product.id)).filter(
        Product.clinic_id == current_user.clinic_id,
        Product.is_active == True
    )
    total_products_result = await db.execute(total_products_query)
    total_products = total_products_result.scalar()
    
    # Low stock products
    low_stock_query = select(func.count(Product.id)).filter(
        Product.clinic_id == current_user.clinic_id,
        Product.is_active == True,
        Product.current_stock <= Product.min_stock,
        Product.current_stock > 0
    )
    low_stock_result = await db.execute(low_stock_query)
    low_stock_products = low_stock_result.scalar()
    
    # Out of stock products
    out_of_stock_query = select(func.count(Product.id)).filter(
        Product.clinic_id == current_user.clinic_id,
        Product.is_active == True,
        Product.current_stock == 0
    )
    out_of_stock_result = await db.execute(out_of_stock_query)
    out_of_stock_products = out_of_stock_result.scalar()
    
    # Total value
    total_value_query = select(func.sum(Product.current_stock * Product.unit_price)).filter(
        Product.clinic_id == current_user.clinic_id,
        Product.is_active == True,
        Product.unit_price.isnot(None)
    )
    total_value_result = await db.execute(total_value_query)
    total_value = total_value_result.scalar() or 0.0
    
    # Recent movements (last 7 days)
    recent_movements_query = select(func.count(StockMovement.id)).filter(
        StockMovement.clinic_id == current_user.clinic_id,
        StockMovement.timestamp >= datetime.now() - timedelta(days=7)
    )
    recent_movements_result = await db.execute(recent_movements_query)
    recent_movements = recent_movements_result.scalar()
    
    # Pending alerts
    pending_alerts_query = select(func.count(StockAlert.id)).filter(
        StockAlert.clinic_id == current_user.clinic_id,
        StockAlert.is_resolved == False
    )
    pending_alerts_result = await db.execute(pending_alerts_query)
    pending_alerts = pending_alerts_result.scalar()
    
    return StockSummary(
        total_products=total_products,
        low_stock_products=low_stock_products,
        out_of_stock_products=out_of_stock_products,
        total_value=float(total_value),
        recent_movements=recent_movements,
        pending_alerts=pending_alerts
    )

# ==================== Helper Functions ====================

def _get_stock_status(current_stock: int, min_stock: int) -> str:
    """Get stock status based on current and minimum stock"""
    if current_stock == 0:
        return "out_of_stock"
    elif current_stock <= min_stock:
        return "low"
    else:
        return "normal"

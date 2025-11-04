from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional

from app.core.auth import get_current_user
from database import get_async_session
from app.models import (
    User, Procedure, ProcedureProduct, Product, Clinic,
    UserRole
)
from app.schemas.procedure import (
    ProcedureCreate, ProcedureUpdate, ProcedureResponse,
    ProcedureProductCreate, ProcedureProductUpdate, ProcedureProductResponse,
    ProcedureWithProductsCreate, ProcedureWithProductsResponse
)

router = APIRouter(tags=["Procedures"])

# ==================== Procedures ====================

@router.post("/procedures", response_model=ProcedureResponse, status_code=status.HTTP_201_CREATED)
async def create_procedure(
    procedure_in: ProcedureCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new procedure
    Requires staff role (admin or secretary)
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can create procedures"
        )
    
    db_procedure = Procedure(clinic_id=current_user.clinic_id, **procedure_in.model_dump())
    db.add(db_procedure)
    await db.commit()
    await db.refresh(db_procedure)
    
    return db_procedure

@router.get("/procedures", response_model=List[ProcedureResponse])
async def get_procedures(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by name or description"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Retrieve a list of procedures
    Allows filtering by active status and search terms
    """
    query = select(Procedure).filter(Procedure.clinic_id == current_user.clinic_id).options(
        selectinload(Procedure.procedure_products).selectinload(ProcedureProduct.product)
    )

    if is_active is not None:
        query = query.filter(Procedure.is_active == is_active)
    if search:
        query = query.filter(
            or_(
                Procedure.name.ilike(f"%{search}%"),
                Procedure.description.ilike(f"%{search}%")
            )
        )
    
    query = query.order_by(Procedure.name)

    procedures_result = await db.execute(query)
    procedures = procedures_result.unique().scalars().all()

    # Convert to response format
    procedure_responses = []
    for procedure in procedures:
        procedure_response = ProcedureResponse.model_validate(procedure)
        procedure_response.procedure_products = [
            ProcedureProductResponse(
                id=pp.id,
                procedure_id=pp.procedure_id,
                product_id=pp.product_id,
                quantity_required=float(pp.quantity_required),
                notes=pp.notes,
                created_at=pp.created_at,
                product_name=pp.product.name if pp.product else None,
                product_unit_of_measure=pp.product.unit_of_measure if pp.product else None
            ) for pp in procedure.procedure_products
        ]
        procedure_responses.append(procedure_response)

    return procedure_responses

@router.get("/procedures/{procedure_id}", response_model=ProcedureResponse)
async def get_procedure(
    procedure_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Retrieve a specific procedure by ID
    """
    procedure_query = select(Procedure).filter(
        Procedure.id == procedure_id,
        Procedure.clinic_id == current_user.clinic_id
    ).options(
        selectinload(Procedure.procedure_products).selectinload(ProcedureProduct.product)
    )
    procedure_result = await db.execute(procedure_query)
    procedure = procedure_result.unique().scalar_one_or_none()

    if not procedure:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")
    
    procedure_response = ProcedureResponse.model_validate(procedure)
    procedure_response.procedure_products = [
        ProcedureProductResponse(
            id=pp.id,
            procedure_id=pp.procedure_id,
            product_id=pp.product_id,
            quantity_required=float(pp.quantity_required),
            notes=pp.notes,
            created_at=pp.created_at,
            product_name=pp.product.name if pp.product else None,
            product_unit_of_measure=pp.product.unit_of_measure if pp.product else None
        ) for pp in procedure.procedure_products
    ]
    
    return procedure_response

@router.put("/procedures/{procedure_id}", response_model=ProcedureResponse)
async def update_procedure(
    procedure_id: int,
    procedure_in: ProcedureUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update an existing procedure
    Requires staff role
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can update procedures"
        )
    
    procedure_query = select(Procedure).filter(
        Procedure.id == procedure_id,
        Procedure.clinic_id == current_user.clinic_id
    )
    procedure_result = await db.execute(procedure_query)
    procedure = procedure_result.scalar_one_or_none()

    if not procedure:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")
    
    update_data = procedure_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(procedure, field, value)
    
    await db.commit()
    await db.refresh(procedure)
    
    return procedure

@router.delete("/procedures/{procedure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_procedure(
    procedure_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Delete a procedure (soft delete by setting is_active to False)
    Requires staff role
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can delete procedures"
        )
    
    procedure_query = select(Procedure).filter(
        Procedure.id == procedure_id,
        Procedure.clinic_id == current_user.clinic_id
    )
    procedure_result = await db.execute(procedure_query)
    procedure = procedure_result.scalar_one_or_none()

    if not procedure:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")
    
    procedure.is_active = False  # Soft delete
    await db.commit()
    
    return {"message": "Procedure deleted successfully"}

# ==================== Procedure Products ====================

@router.post("/procedures/{procedure_id}/products", response_model=ProcedureProductResponse, status_code=status.HTTP_201_CREATED)
async def add_product_to_procedure(
    procedure_id: int,
    product_in: ProcedureProductCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Add a product to a procedure's technical sheet
    Requires staff role
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can modify procedure products"
        )
    
    # Verify procedure exists and belongs to clinic
    procedure_query = select(Procedure).filter(
        Procedure.id == procedure_id,
        Procedure.clinic_id == current_user.clinic_id
    )
    procedure_result = await db.execute(procedure_query)
    procedure = procedure_result.scalar_one_or_none()
    
    if not procedure:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")
    
    # Verify product exists and belongs to clinic
    product_query = select(Product).filter(
        Product.id == product_in.product_id,
        Product.clinic_id == current_user.clinic_id
    )
    product_result = await db.execute(product_query)
    product = product_result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    
    # Check if product is already in procedure
    existing_query = select(ProcedureProduct).filter(
        ProcedureProduct.procedure_id == procedure_id,
        ProcedureProduct.product_id == product_in.product_id
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product is already in this procedure's technical sheet"
        )
    
    db_procedure_product = ProcedureProduct(
        procedure_id=procedure_id,
        **product_in.model_dump()
    )
    db.add(db_procedure_product)
    await db.commit()
    await db.refresh(db_procedure_product)
    
    # Load with product information for response
    loaded_query = select(ProcedureProduct).options(
        joinedload(ProcedureProduct.product)
    ).filter(ProcedureProduct.id == db_procedure_product.id)
    loaded_result = await db.execute(loaded_query)
    loaded_pp = loaded_result.scalar_one()
    
    return ProcedureProductResponse(
        id=loaded_pp.id,
        procedure_id=loaded_pp.procedure_id,
        product_id=loaded_pp.product_id,
        quantity_required=float(loaded_pp.quantity_required),
        notes=loaded_pp.notes,
        created_at=loaded_pp.created_at,
        product_name=loaded_pp.product.name,
        product_unit_of_measure=loaded_pp.product.unit_of_measure
    )

@router.put("/procedure-products/{procedure_product_id}", response_model=ProcedureProductResponse)
async def update_procedure_product(
    procedure_product_id: int,
    product_in: ProcedureProductUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update a product in a procedure's technical sheet
    Requires staff role
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can modify procedure products"
        )
    
    # Get procedure product with procedure and product info
    pp_query = select(ProcedureProduct).options(
        joinedload(ProcedureProduct.procedure),
        joinedload(ProcedureProduct.product)
    ).filter(
        ProcedureProduct.id == procedure_product_id,
        ProcedureProduct.procedure.has(Procedure.clinic_id == current_user.clinic_id)
    )
    pp_result = await db.execute(pp_query)
    procedure_product = pp_result.scalar_one_or_none()
    
    if not procedure_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure product not found")
    
    update_data = product_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(procedure_product, field, value)
    
    await db.commit()
    await db.refresh(procedure_product)
    
    return ProcedureProductResponse(
        id=procedure_product.id,
        procedure_id=procedure_product.procedure_id,
        product_id=procedure_product.product_id,
        quantity_required=float(procedure_product.quantity_required),
        notes=procedure_product.notes,
        created_at=procedure_product.created_at,
        product_name=procedure_product.product.name,
        product_unit_of_measure=procedure_product.product.unit_of_measure
    )

@router.delete("/procedure-products/{procedure_product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_product_from_procedure(
    procedure_product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Remove a product from a procedure's technical sheet
    Requires staff role
    """
    # Check if user has permission
    if current_user.role not in [UserRole.ADMIN, UserRole.SECRETARY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can modify procedure products"
        )
    
    # Get procedure product
    pp_query = select(ProcedureProduct).options(
        joinedload(ProcedureProduct.procedure)
    ).filter(
        ProcedureProduct.id == procedure_product_id,
        ProcedureProduct.procedure.has(Procedure.clinic_id == current_user.clinic_id)
    )
    pp_result = await db.execute(pp_query)
    procedure_product = pp_result.scalar_one_or_none()
    
    if not procedure_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure product not found")
    
    await db.delete(procedure_product)
    await db.commit()
    
    return {"message": "Product removed from procedure successfully"}

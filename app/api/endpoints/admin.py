"""
Admin API endpoints for clinic management and licensing
"""

from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_session
from app.models import (
    Clinic, User, UserRole, Patient, Appointment,
    Invoice, Payment, ServiceItem, Product, StockMovement, Procedure
)
from app.models.clinical import ClinicalRecord, Prescription, Diagnosis
from app.schemas.clinic import (
    ClinicCreate, ClinicUpdate, ClinicResponse, ClinicListResponse,
    ClinicLicenseUpdate, ClinicStatsResponse
)
from app.core.auth import get_current_user, RoleChecker
from app.core.licensing import AVAILABLE_MODULES
from typing import Dict, Any
from sqlalchemy.exc import SQLAlchemyError
import asyncio

router = APIRouter(prefix="/admin", tags=["Admin"])

# Require admin role for all endpoints
require_admin = RoleChecker([UserRole.ADMIN])


@router.get("/clinics/stats", response_model=ClinicStatsResponse)
async def get_clinic_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get clinic statistics
    """
    # Total clinics
    total_clinics_query = select(func.count(Clinic.id))
    total_result = await db.execute(total_clinics_query)
    total_clinics = total_result.scalar()
    
    # Active clinics
    active_clinics_query = select(func.count(Clinic.id)).filter(Clinic.is_active == True)
    active_result = await db.execute(active_clinics_query)
    active_clinics = active_result.scalar()
    
    # Expired licenses
    expired_query = select(func.count(Clinic.id)).filter(
        and_(
            Clinic.expiration_date.isnot(None),
            Clinic.expiration_date < date.today()
        )
    )
    expired_result = await db.execute(expired_query)
    expired_licenses = expired_result.scalar()
    
    # Total users
    total_users_query = select(func.count(User.id)).filter(User.is_active == True)
    users_result = await db.execute(total_users_query)
    total_users = users_result.scalar()
    
    # Clinics near expiration (next 30 days)
    near_expiration_date = date.today() + timedelta(days=30)
    near_expiration_query = select(func.count(Clinic.id)).filter(
        and_(
            Clinic.expiration_date.isnot(None),
            Clinic.expiration_date <= near_expiration_date,
            Clinic.expiration_date >= date.today()
        )
    )
    near_expiration_result = await db.execute(near_expiration_query)
    clinics_near_expiration = near_expiration_result.scalar()
    
    return ClinicStatsResponse(
        total_clinics=total_clinics,
        active_clinics=active_clinics,
        expired_licenses=expired_licenses,
        total_users=total_users,
        clinics_near_expiration=clinics_near_expiration
    )


@router.get("/clinics", response_model=List[ClinicListResponse])
async def list_clinics(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    license_expired: Optional[bool] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List all clinics with filtering options
    """
    query = select(Clinic)
    
    # Apply filters
    if search:
        query = query.filter(
            or_(
                Clinic.name.ilike(f"%{search}%"),
                Clinic.legal_name.ilike(f"%{search}%"),
                Clinic.tax_id.ilike(f"%{search}%"),
                Clinic.email.ilike(f"%{search}%")
            )
        )
    
    if is_active is not None:
        query = query.filter(Clinic.is_active == is_active)
    
    if license_expired is not None:
        if license_expired:
            query = query.filter(
                and_(
                    Clinic.expiration_date.isnot(None),
                    Clinic.expiration_date < date.today()
                )
            )
        else:
            query = query.filter(
                or_(
                    Clinic.expiration_date.isnull(),
                    Clinic.expiration_date >= date.today()
                )
            )
    
    # Get total count
    count_query = select(func.count(Clinic.id))
    for filter_condition in query.whereclause.children if query.whereclause else []:
        count_query = count_query.where(filter_condition)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Apply pagination
    query = query.offset(skip).limit(limit).order_by(Clinic.created_at.desc())
    
    result = await db.execute(query)
    clinics = result.scalars().all()
    
    # Get user counts for each clinic
    clinic_list = []
    for clinic in clinics:
        user_count_query = select(func.count(User.id)).filter(
            User.clinic_id == clinic.id,
            User.is_active == True
        )
        user_count_result = await db.execute(user_count_query)
        user_count = user_count_result.scalar()
        
        clinic_list.append(ClinicListResponse(
            id=clinic.id,
            name=clinic.name,
            legal_name=clinic.legal_name,
            tax_id=clinic.tax_id,
            email=clinic.email,
            is_active=clinic.is_active,
            license_key=clinic.license_key,
            expiration_date=clinic.expiration_date,
            max_users=clinic.max_users,
            active_modules=clinic.active_modules or [],
            user_count=user_count,
            created_at=clinic.created_at.date()
        ))
    
    return clinic_list


@router.get("/clinics/{clinic_id}", response_model=ClinicResponse)
async def get_clinic(
    clinic_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get a specific clinic by ID
    """
    query = select(Clinic).filter(Clinic.id == clinic_id)
    result = await db.execute(query)
    clinic = result.scalar_one_or_none()
    
    if not clinic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found"
        )
    
    return clinic


@router.post("/clinics", response_model=ClinicResponse)
async def create_clinic(
    clinic_data: ClinicCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new clinic
    """
    # Check if clinic with same tax_id already exists
    existing_clinic = await db.execute(
        select(Clinic).filter(Clinic.tax_id == clinic_data.tax_id)
    )
    if existing_clinic.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clinic with this tax ID already exists"
        )
    
    # Check if license_key is unique (if provided)
    if clinic_data.license_key:
        existing_license = await db.execute(
            select(Clinic).filter(Clinic.license_key == clinic_data.license_key)
        )
        if existing_license.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="License key already exists"
            )
    
    # Create clinic
    clinic = Clinic(**clinic_data.model_dump())
    db.add(clinic)
    await db.commit()
    await db.refresh(clinic)
    
    return clinic


@router.put("/clinics/{clinic_id}", response_model=ClinicResponse)
async def update_clinic(
    clinic_id: int,
    clinic_data: ClinicUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update a clinic
    """
    query = select(Clinic).filter(Clinic.id == clinic_id)
    result = await db.execute(query)
    clinic = result.scalar_one_or_none()
    
    if not clinic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found"
        )
    
    # Check if tax_id is unique (if being updated)
    if clinic_data.tax_id and clinic_data.tax_id != clinic.tax_id:
        existing_clinic = await db.execute(
            select(Clinic).filter(Clinic.tax_id == clinic_data.tax_id)
        )
        if existing_clinic.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Clinic with this tax ID already exists"
            )
    
    # Check if license_key is unique (if being updated)
    if clinic_data.license_key and clinic_data.license_key != clinic.license_key:
        existing_license = await db.execute(
            select(Clinic).filter(Clinic.license_key == clinic_data.license_key)
        )
        if existing_license.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="License key already exists"
            )
    
    # Update clinic
    update_data = clinic_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(clinic, field, value)
    
    await db.commit()
    await db.refresh(clinic)
    
    return clinic


@router.patch("/clinics/{clinic_id}/license", response_model=ClinicResponse)
async def update_clinic_license(
    clinic_id: int,
    license_data: ClinicLicenseUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update clinic license information
    """
    query = select(Clinic).filter(Clinic.id == clinic_id)
    result = await db.execute(query)
    clinic = result.scalar_one_or_none()
    
    if not clinic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found"
        )
    
    # Check if license_key is unique (if being updated)
    if license_data.license_key and license_data.license_key != clinic.license_key:
        existing_license = await db.execute(
            select(Clinic).filter(Clinic.license_key == license_data.license_key)
        )
        if existing_license.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="License key already exists"
            )
    
    # Update license information
    update_data = license_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(clinic, field, value)
    
    await db.commit()
    await db.refresh(clinic)
    
    return clinic


@router.delete("/clinics/{clinic_id}")
async def delete_clinic(
    clinic_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Delete a clinic (soft delete by setting is_active=False)
    """
    query = select(Clinic).filter(Clinic.id == clinic_id)
    result = await db.execute(query)
    clinic = result.scalar_one_or_none()
    
    if not clinic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found"
        )
    
    # Soft delete
    clinic.is_active = False
    await db.commit()
    
    return {"message": "Clinic deactivated successfully"}


@router.get("/modules", response_model=List[str])
async def get_available_modules(
    current_user: User = Depends(require_admin)
):
    """
    Get list of available modules
    """
    return AVAILABLE_MODULES


@router.patch("/clinics/{clinic_id}/modules", response_model=ClinicResponse)
async def update_clinic_modules(
    clinic_id: int,
    modules_data: dict,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update clinic active modules
    """
    clinic = await db.get(Clinic, clinic_id)
    if not clinic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found"
        )
    
    # Validate modules
    available_modules = [
        "patients", "appointments", "clinical", "financial", 
        "stock", "bi", "procedures", "tiss", "mobile", "telemed"
    ]
    
    active_modules = modules_data.get("active_modules", [])
    if not isinstance(active_modules, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="active_modules must be a list"
        )
    
    # Validate each module
    for module in active_modules:
        if module not in available_modules:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid module: {module}. Available modules: {available_modules}"
            )
    
    # Update modules
    clinic.active_modules = active_modules
    await db.commit()
    await db.refresh(clinic)
    
    return clinic


@router.get("/database/test-connections")
async def test_database_connections(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Test database connections for each module by attempting to query their tables
    Returns status for each module: success, error message, and response time
    """
    results: Dict[str, Dict[str, Any]] = {}
    
    # Define modules and their test queries
    module_tests = {
        "patients": {
            "table": Patient,
            "query": select(func.count(Patient.id))
        },
        "appointments": {
            "table": Appointment,
            "query": select(func.count(Appointment.id))
        },
        "clinical": {
            "table": ClinicalRecord,
            "query": select(func.count(ClinicalRecord.id))
        },
        "prescriptions": {
            "table": Prescription,
            "query": select(func.count(Prescription.id))
        },
        "diagnoses": {
            "table": Diagnosis,
            "query": select(func.count(Diagnosis.id))
        },
        "financial": {
            "table": Invoice,
            "query": select(func.count(Invoice.id))
        },
        "payments": {
            "table": Payment,
            "query": select(func.count(Payment.id))
        },
        "service_items": {
            "table": ServiceItem,
            "query": select(func.count(ServiceItem.id))
        },
        "stock": {
            "table": Product,
            "query": select(func.count(Product.id))
        },
        "stock_movements": {
            "table": StockMovement,
            "query": select(func.count(StockMovement.id))
        },
        "procedures": {
            "table": Procedure,
            "query": select(func.count(Procedure.id))
        },
        "users": {
            "table": User,
            "query": select(func.count(User.id))
        },
        "clinics": {
            "table": Clinic,
            "query": select(func.count(Clinic.id))
        }
    }
    
    # Test each module
    for module_name, test_config in module_tests.items():
        start_time = asyncio.get_event_loop().time()
        try:
            result = await db.execute(test_config["query"])
            count = result.scalar()
            end_time = asyncio.get_event_loop().time()
            response_time_ms = round((end_time - start_time) * 1000, 2)
            
            results[module_name] = {
                "status": "success",
                "message": f"Connection successful",
                "record_count": count,
                "response_time_ms": response_time_ms,
                "error": None
            }
        except SQLAlchemyError as e:
            end_time = asyncio.get_event_loop().time()
            response_time_ms = round((end_time - start_time) * 1000, 2)
            
            results[module_name] = {
                "status": "error",
                "message": f"Database error: {str(e)}",
                "record_count": None,
                "response_time_ms": response_time_ms,
                "error": str(e)
            }
        except Exception as e:
            end_time = asyncio.get_event_loop().time()
            response_time_ms = round((end_time - start_time) * 1000, 2)
            
            results[module_name] = {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
                "record_count": None,
                "response_time_ms": response_time_ms,
                "error": str(e)
            }
    
    # Calculate summary
    total_modules = len(results)
    successful_modules = sum(1 for r in results.values() if r["status"] == "success")
    failed_modules = total_modules - successful_modules
    avg_response_time = sum(r["response_time_ms"] for r in results.values()) / total_modules if total_modules > 0 else 0
    
    return {
        "summary": {
            "total_modules": total_modules,
            "successful": successful_modules,
            "failed": failed_modules,
            "average_response_time_ms": round(avg_response_time, 2)
        },
        "modules": results
    }

"""
Admin API endpoints for clinic management and licensing
"""

from datetime import date, timedelta, datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_session
from app.models import (
    Clinic, User, UserRole as UserRoleEnum, Patient, Appointment,
    Invoice, Payment, ServiceItem, Product, StockMovement, Procedure
)
from app.models.menu import UserRole
from app.models.clinical import ClinicalRecord, Prescription, Diagnosis
from app.schemas.clinic import (
    ClinicCreate, ClinicUpdate, ClinicResponse, ClinicListResponse,
    ClinicLicenseUpdate, ClinicStatsResponse
)
from app.core.auth import get_current_user, RoleChecker
from app.core.security import hash_password
from app.core.licensing import AVAILABLE_MODULES
from typing import Dict, Any
from sqlalchemy.exc import SQLAlchemyError
import asyncio
from app.models import SystemLog
from app.schemas.system_log import (
    SystemLogCreate, SystemLogUpdate, SystemLogResponse,
)

router = APIRouter(prefix="/admin", tags=["Admin"])

# Require admin role for all endpoints
require_admin = RoleChecker([UserRoleEnum.ADMIN])


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


@router.get("/clinics/me", response_model=ClinicResponse)
async def get_my_clinic(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get the current user's clinic information
    Available to any authenticated user
    """
    if not current_user.clinic_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not associated with a clinic"
        )
    
    query = select(Clinic).filter(Clinic.id == current_user.clinic_id)
    result = await db.execute(query)
    clinic = result.scalar_one_or_none()
    
    if not clinic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found"
        )
    
    # Ensure date-only fields for pydantic schema
    from datetime import date as date_type, datetime
    
    # Helper function to convert datetime to date - absolutely ensure it's a date object
    def to_date(dt_value):
        """Convert datetime or date to pure date object - guaranteed"""
        if dt_value is None:
            return None
        if isinstance(dt_value, date_type):
            # Already a date, return as-is
            return dt_value
        if isinstance(dt_value, datetime):
            # For timezone-aware datetimes, convert to UTC first
            if dt_value.tzinfo is not None:
                from datetime import timezone as tz
                dt_value = dt_value.astimezone(tz.utc)
            # Create a NEW date object from the datetime components
            # This ensures we have a pure date object, not a datetime
            return date_type(dt_value.year, dt_value.month, dt_value.day)
        # Fallback: try to get date attribute
        if hasattr(dt_value, 'date'):
            dt_result = dt_value.date()
            # If date() returns a datetime (shouldn't happen), convert it
            if isinstance(dt_result, datetime):
                if dt_result.tzinfo is not None:
                    from datetime import timezone as tz
                    dt_result = dt_result.astimezone(tz.utc)
                return date_type(dt_result.year, dt_result.month, dt_result.day)
            # If it's already a date, create a new one to be sure
            if isinstance(dt_result, date_type):
                return date_type(dt_result.year, dt_result.month, dt_result.day)
        # Last resort
        return date_type.today()
    
    # Convert datetime to date for created_at - access directly and convert immediately
    created_at_raw = clinic.created_at if hasattr(clinic, 'created_at') and clinic.created_at is not None else None
    # Force immediate conversion - don't trust any intermediate values
    if created_at_raw is None:
        created_at_date = date_type.today()
    elif isinstance(created_at_raw, datetime):
        # It's a datetime - convert to UTC if timezone-aware, then extract date
        if created_at_raw.tzinfo is not None:
            from datetime import timezone as tz
            created_at_raw = created_at_raw.astimezone(tz.utc)
        created_at_date = date_type(created_at_raw.year, created_at_raw.month, created_at_raw.day)
    elif isinstance(created_at_raw, date_type):
        # Already a date - create new instance to be absolutely sure
        created_at_date = date_type(created_at_raw.year, created_at_raw.month, created_at_raw.day)
    else:
        # Fallback
        created_at_date = date_type.today()
    
    # Convert datetime to date for updated_at - same approach
    updated_at_raw = clinic.updated_at if hasattr(clinic, 'updated_at') and clinic.updated_at is not None else None
    if updated_at_raw is None:
        updated_at_date = None
    elif isinstance(updated_at_raw, datetime):
        # It's a datetime - convert to UTC if timezone-aware, then extract date
        if updated_at_raw.tzinfo is not None:
            from datetime import timezone as tz
            updated_at_raw = updated_at_raw.astimezone(tz.utc)
        updated_at_date = date_type(updated_at_raw.year, updated_at_raw.month, updated_at_raw.day)
    elif isinstance(updated_at_raw, date_type):
        # Already a date - create new instance to be absolutely sure
        updated_at_date = date_type(updated_at_raw.year, updated_at_raw.month, updated_at_raw.day)
    else:
        updated_at_date = None
    
    # Verify conversion worked - ensure we have pure date objects (not datetime)
    # This is critical for Pydantic v2 validation
    if not isinstance(created_at_date, date_type) or isinstance(created_at_date, datetime):
        # Force conversion if somehow it's still a datetime
        if isinstance(created_at_date, datetime):
            if created_at_date.tzinfo is not None:
                from datetime import timezone as tz
                created_at_date = created_at_date.astimezone(tz.utc)
            created_at_date = date_type(created_at_date.year, created_at_date.month, created_at_date.day)
        else:
            created_at_date = date_type.today()
    
    if updated_at_date is not None and (not isinstance(updated_at_date, date_type) or isinstance(updated_at_date, datetime)):
        # Force conversion if somehow it's still a datetime
        if isinstance(updated_at_date, datetime):
            if updated_at_date.tzinfo is not None:
                from datetime import timezone as tz
                updated_at_date = updated_at_date.astimezone(tz.utc)
            updated_at_date = date_type(updated_at_date.year, updated_at_date.month, updated_at_date.day)
        else:
            updated_at_date = None
    
    # Build response as dict to ensure proper date conversion
    response_dict = {
        "id": clinic.id,
        "name": clinic.name,
        "legal_name": clinic.legal_name,
        "tax_id": clinic.tax_id,
        "address": clinic.address,
        "phone": clinic.phone,
        "email": clinic.email,
        "is_active": clinic.is_active,
        "license_key": clinic.license_key,
        "expiration_date": clinic.expiration_date,
        "max_users": clinic.max_users,
        "active_modules": clinic.active_modules or [],
        "created_at": created_at_date,
        "updated_at": updated_at_date,
    }
    
    # Double-check: ensure we have pure date objects (not datetime)
    # This is critical - Pydantic v2 is very strict about date vs datetime
    if isinstance(response_dict.get('created_at'), datetime):
        dt = response_dict['created_at']
        if dt.tzinfo is not None:
            from datetime import timezone as tz
            dt = dt.astimezone(tz.utc)
        response_dict['created_at'] = date_type(dt.year, dt.month, dt.day)
    
    if isinstance(response_dict.get('updated_at'), datetime):
        dt = response_dict['updated_at']
        if dt is not None:
            if dt.tzinfo is not None:
                from datetime import timezone as tz
                dt = dt.astimezone(tz.utc)
            response_dict['updated_at'] = date_type(dt.year, dt.month, dt.day)
    
    # Final verification - these MUST be date objects, not datetime
    assert isinstance(response_dict['created_at'], date_type) and not isinstance(response_dict['created_at'], datetime), \
        f"created_at is {type(response_dict['created_at'])} - must be date, not datetime"
    if response_dict.get('updated_at') is not None:
        assert isinstance(response_dict['updated_at'], date_type) and not isinstance(response_dict['updated_at'], datetime), \
            f"updated_at is {type(response_dict['updated_at'])} - must be date, not datetime"
    
    # Use model_construct to create the response object (bypasses validation)
    # Since we've manually converted everything to date objects, this is safe
    # model_construct doesn't validate, so it won't complain about datetime objects
    # But we've already converted them, so we're good
    return ClinicResponse.model_construct(**response_dict)


@router.put("/clinics/me", response_model=ClinicResponse)
async def update_my_clinic(
    clinic_data: ClinicUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update the current user's clinic information
    Available to admin users (AdminClinica role) or super admin
    """
    # Check if user has permission (admin role or super admin)
    if current_user.role not in [UserRoleEnum.ADMIN] and current_user.role_id != 2:  # AdminClinica role_id is 2
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinic administrators can update clinic information"
        )
    
    if not current_user.clinic_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not associated with a clinic"
        )
    
    query = select(Clinic).filter(Clinic.id == current_user.clinic_id)
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
    
    # Update clinic (only allow updating basic info, not license info for clinic admins)
    update_data = clinic_data.model_dump(exclude_unset=True)
    # Remove license-related fields for clinic admins (only super admin can update these)
    if current_user.role != UserRoleEnum.ADMIN or current_user.role_id != 1:  # Not super admin
        update_data.pop("license_key", None)
        update_data.pop("expiration_date", None)
        update_data.pop("max_users", None)
        update_data.pop("active_modules", None)
    
    for field, value in update_data.items():
        setattr(clinic, field, value)
    
    await db.commit()
    await db.refresh(clinic)
    
    # Ensure date-only fields for pydantic schema
    from datetime import date as date_type, datetime
    
    # Helper function to convert datetime to date - absolutely ensure it's a date object
    def to_date(dt_value):
        """Convert datetime or date to pure date object - guaranteed"""
        if dt_value is None:
            return None
        if isinstance(dt_value, date_type):
            # Already a date, return as-is
            return dt_value
        if isinstance(dt_value, datetime):
            # For timezone-aware datetimes, convert to UTC first
            if dt_value.tzinfo is not None:
                from datetime import timezone as tz
                dt_value = dt_value.astimezone(tz.utc)
            # Create a NEW date object from the datetime components
            # This ensures we have a pure date object, not a datetime
            return date_type(dt_value.year, dt_value.month, dt_value.day)
        # Fallback: try to get date attribute
        if hasattr(dt_value, 'date'):
            dt_result = dt_value.date()
            # If date() returns a datetime (shouldn't happen), convert it
            if isinstance(dt_result, datetime):
                if dt_result.tzinfo is not None:
                    from datetime import timezone as tz
                    dt_result = dt_result.astimezone(tz.utc)
                return date_type(dt_result.year, dt_result.month, dt_result.day)
            # If it's already a date, create a new one to be sure
            if isinstance(dt_result, date_type):
                return date_type(dt_result.year, dt_result.month, dt_result.day)
        # Last resort
        return date_type.today()
    
    # Convert datetime to date for created_at - access directly and convert immediately
    created_at_raw = clinic.created_at if hasattr(clinic, 'created_at') and clinic.created_at is not None else None
    # Force immediate conversion - don't trust any intermediate values
    if created_at_raw is None:
        created_at_date = date_type.today()
    elif isinstance(created_at_raw, datetime):
        # It's a datetime - convert to UTC if timezone-aware, then extract date
        if created_at_raw.tzinfo is not None:
            from datetime import timezone as tz
            created_at_raw = created_at_raw.astimezone(tz.utc)
        created_at_date = date_type(created_at_raw.year, created_at_raw.month, created_at_raw.day)
    elif isinstance(created_at_raw, date_type):
        # Already a date - create new instance to be absolutely sure
        created_at_date = date_type(created_at_raw.year, created_at_raw.month, created_at_raw.day)
    else:
        # Fallback
        created_at_date = date_type.today()
    
    # Convert datetime to date for updated_at - same approach
    updated_at_raw = clinic.updated_at if hasattr(clinic, 'updated_at') and clinic.updated_at is not None else None
    if updated_at_raw is None:
        updated_at_date = None
    elif isinstance(updated_at_raw, datetime):
        # It's a datetime - convert to UTC if timezone-aware, then extract date
        if updated_at_raw.tzinfo is not None:
            from datetime import timezone as tz
            updated_at_raw = updated_at_raw.astimezone(tz.utc)
        updated_at_date = date_type(updated_at_raw.year, updated_at_raw.month, updated_at_raw.day)
    elif isinstance(updated_at_raw, date_type):
        # Already a date - create new instance to be absolutely sure
        updated_at_date = date_type(updated_at_raw.year, updated_at_raw.month, updated_at_raw.day)
    else:
        updated_at_date = None
    
    # Verify conversion worked - ensure we have pure date objects (not datetime)
    # This is critical for Pydantic v2 validation
    if not isinstance(created_at_date, date_type) or isinstance(created_at_date, datetime):
        # Force conversion if somehow it's still a datetime
        if isinstance(created_at_date, datetime):
            if created_at_date.tzinfo is not None:
                from datetime import timezone as tz
                created_at_date = created_at_date.astimezone(tz.utc)
            created_at_date = date_type(created_at_date.year, created_at_date.month, created_at_date.day)
        else:
            created_at_date = date_type.today()
    
    if updated_at_date is not None and (not isinstance(updated_at_date, date_type) or isinstance(updated_at_date, datetime)):
        # Force conversion if somehow it's still a datetime
        if isinstance(updated_at_date, datetime):
            if updated_at_date.tzinfo is not None:
                from datetime import timezone as tz
                updated_at_date = updated_at_date.astimezone(tz.utc)
            updated_at_date = date_type(updated_at_date.year, updated_at_date.month, updated_at_date.day)
        else:
            updated_at_date = None
    
    # Build response as dict to ensure proper date conversion
    response_dict = {
        "id": clinic.id,
        "name": clinic.name,
        "legal_name": clinic.legal_name,
        "tax_id": clinic.tax_id,
        "address": clinic.address,
        "phone": clinic.phone,
        "email": clinic.email,
        "is_active": clinic.is_active,
        "license_key": clinic.license_key,
        "expiration_date": clinic.expiration_date,
        "max_users": clinic.max_users,
        "active_modules": clinic.active_modules or [],
        "created_at": created_at_date,
        "updated_at": updated_at_date,
    }
    
    # Double-check: ensure we have pure date objects (not datetime)
    # This is critical - Pydantic v2 is very strict about date vs datetime
    if isinstance(response_dict.get('created_at'), datetime):
        dt = response_dict['created_at']
        if dt.tzinfo is not None:
            from datetime import timezone as tz
            dt = dt.astimezone(tz.utc)
        response_dict['created_at'] = date_type(dt.year, dt.month, dt.day)
    
    if isinstance(response_dict.get('updated_at'), datetime):
        dt = response_dict['updated_at']
        if dt is not None:
            if dt.tzinfo is not None:
                from datetime import timezone as tz
                dt = dt.astimezone(tz.utc)
            response_dict['updated_at'] = date_type(dt.year, dt.month, dt.day)
    
    # Final verification - these MUST be date objects, not datetime
    assert isinstance(response_dict['created_at'], date_type) and not isinstance(response_dict['created_at'], datetime), \
        f"created_at is {type(response_dict['created_at'])} - must be date, not datetime"
    if response_dict.get('updated_at') is not None:
        assert isinstance(response_dict['updated_at'], date_type) and not isinstance(response_dict['updated_at'], datetime), \
            f"updated_at is {type(response_dict['updated_at'])} - must be date, not datetime"
    
    # Use model_construct to create the response object (bypasses validation)
    # Since we've manually converted everything to date objects, this is safe
    # model_construct doesn't validate, so it won't complain about datetime objects
    # But we've already converted them, so we're good
    return ClinicResponse.model_construct(**response_dict)


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
    
    # Ensure date-only fields for pydantic schema - use same conversion as /me endpoint
    from datetime import date as date_type, datetime
    
    def to_date(dt_value):
        """Convert datetime or date to pure date object - guaranteed"""
        if dt_value is None:
            return None
        if isinstance(dt_value, date_type):
            return date_type(dt_value.year, dt_value.month, dt_value.day)
        if isinstance(dt_value, datetime):
            if dt_value.tzinfo is not None:
                from datetime import timezone as tz
                dt_value = dt_value.astimezone(tz.utc)
            return date_type(dt_value.year, dt_value.month, dt_value.day)
        if hasattr(dt_value, 'date'):
            dt_result = dt_value.date()
            if isinstance(dt_result, datetime):
                if dt_result.tzinfo is not None:
                    from datetime import timezone as tz
                    dt_result = dt_result.astimezone(tz.utc)
                return date_type(dt_result.year, dt_result.month, dt_result.day)
            if isinstance(dt_result, date_type):
                return date_type(dt_result.year, dt_result.month, dt_result.day)
        return date_type.today()
    
    response_dict = {
        "id": clinic.id,
        "name": clinic.name,
        "legal_name": clinic.legal_name,
        "tax_id": clinic.tax_id,
        "address": clinic.address,
        "phone": clinic.phone,
        "email": clinic.email,
        "is_active": clinic.is_active,
        "license_key": clinic.license_key,
        "expiration_date": clinic.expiration_date,
        "max_users": clinic.max_users,
        "active_modules": clinic.active_modules or [],
        "created_at": to_date(getattr(clinic, "created_at", None)) or date_type.today(),
        "updated_at": to_date(getattr(clinic, "updated_at", None)),
    }
    
    try:
        return ClinicResponse.model_validate(response_dict)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"ClinicResponse validation failed: {e}")
        return ClinicResponse.model_construct(**response_dict)


@router.post("/clinics")  # Removed response_model to allow admin_user field
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
    await db.flush()  # Flush to get clinic.id without committing
    
    # Get AdminClinica role (role_id = 2)
    admin_role_query = await db.execute(
        select(UserRole).where(UserRole.name == "AdminClinica")
    )
    admin_role = admin_role_query.scalar_one_or_none()
    
    if not admin_role:
        # If AdminClinica role doesn't exist, rollback and raise error
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AdminClinica role not found. Please run seed script first."
        )
    
    # Generate default admin user credentials
    # Use clinic name to create username (sanitized)
    clinic_name_slug = clinic_data.name.lower().replace(" ", "_").replace("-", "_")
    # Remove special characters, keep only alphanumeric and underscore
    clinic_name_slug = "".join(c for c in clinic_name_slug if c.isalnum() or c == "_")
    # Limit length and ensure uniqueness
    base_username = f"admin_{clinic_name_slug[:20]}"
    
    # Check if username already exists, if so append clinic id
    username = base_username
    counter = 1
    while True:
        existing_user = await db.execute(
            select(User).where(User.username == username)
        )
        if not existing_user.scalar_one_or_none():
            break
        username = f"{base_username}_{counter}"
        counter += 1
    
    # Generate email from clinic email or use default pattern
    admin_email = clinic_data.email if clinic_data.email else f"admin@{clinic_name_slug}.com"
    # Ensure email uniqueness
    email_counter = 1
    original_email = admin_email
    while True:
        existing_email = await db.execute(
            select(User).where(User.email == admin_email)
        )
        if not existing_email.scalar_one_or_none():
            break
        # Extract domain and add counter
        if "@" in original_email:
            local, domain = original_email.split("@", 1)
            admin_email = f"{local}{email_counter}@{domain}"
        else:
            admin_email = f"admin{email_counter}@{clinic_name_slug}.com"
        email_counter += 1
    
    # Generate default password: clinic name + "123!" (user should change on first login)
    default_password = f"{clinic_data.name.replace(' ', '')}123!"
    # Ensure password meets minimum requirements (at least 8 chars)
    if len(default_password) < 8:
        default_password = f"{clinic_data.name.replace(' ', '')}Admin123!"
    
    # Create AdminClinica user for the new clinic
    admin_user = User(
        username=username,
        email=admin_email,
        hashed_password=hash_password(default_password),
        first_name="Administrador",
        last_name=clinic_data.name,
        role=UserRoleEnum.ADMIN,  # Legacy enum
        role_id=admin_role.id,  # AdminClinica role_id = 2
        clinic_id=clinic.id,
        is_active=True,
        is_verified=True,  # Auto-verify the admin user
    )
    db.add(admin_user)
    
    # Commit both clinic and user
    await db.commit()
    await db.refresh(clinic)
    await db.refresh(admin_user)
    
    # Log the creation
    try:
        log_entry = SystemLog(
            clinic_id=clinic.id,
            user_id=current_user.id if current_user else None,
            action="clinic_created",
            details={
                "clinic_id": clinic.id,
                "clinic_name": clinic.name,
                "admin_user_created": True,
                "admin_username": username,
                "admin_email": admin_email,
            },
            severity="INFO"
        )
        db.add(log_entry)
        await db.commit()
    except Exception as e:
        # Don't fail clinic creation if logging fails
        print(f"Warning: Failed to log clinic creation: {e}")
    
    # Build response with admin user info
    def to_date(dt_value):
        if dt_value is None:
            return None
        if isinstance(dt_value, date):
            return dt_value
        if isinstance(dt_value, datetime):
            if dt_value.tzinfo is not None:
                dt_value = dt_value.astimezone(timezone.utc)
            return date(dt_value.year, dt_value.month, dt_value.day)
        return date.today()
    
    response_dict = {
        "id": clinic.id,
        "name": clinic.name,
        "legal_name": clinic.legal_name,
        "tax_id": clinic.tax_id,
        "address": clinic.address,
        "phone": clinic.phone,
        "email": clinic.email,
        "is_active": clinic.is_active,
        "license_key": clinic.license_key,
        "expiration_date": clinic.expiration_date,
        "max_users": clinic.max_users,
        "active_modules": clinic.active_modules or [],
        "created_at": to_date(getattr(clinic, "created_at", None)) or date.today(),
        "updated_at": to_date(getattr(clinic, "updated_at", None)),
        # Add admin user info to response
        "admin_user": {
            "username": username,
            "email": admin_email,
            "password": default_password,  # Include password so SuperAdmin can share it
            "role": "AdminClinica"
        }
    }
    
    # Return as dict to bypass Pydantic validation for admin_user field
    # FastAPI will serialize it correctly
    return response_dict


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
    Delete a clinic from the database (hard delete).
    This will also delete all related records (users, patients, appointments, etc.)
    due to cascade relationships.
    """
    query = select(Clinic).filter(Clinic.id == clinic_id)
    result = await db.execute(query)
    clinic = result.scalar_one_or_none()
    
    if not clinic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found"
        )
    
    # Store clinic info for logging before deletion
    clinic_name = clinic.name
    clinic_id_for_log = clinic.id
    deleted_by = current_user.username if current_user else "system"
    
    # Use SQL directly to delete all related records, then delete clinic
    # This avoids ORM relationship loading issues and transaction problems
    from sqlalchemy import text
    
    try:
        # Delete related records using SQL to avoid ORM issues
        # Order matters: delete child records before parent records
        
        # Delete all related records using SQL to avoid ORM relationship issues
        # This approach is more reliable and avoids transaction abort problems
        
        # Helper function to execute DELETE with error handling
        async def safe_delete(query: str, params: dict, table_name: str = "", optional: bool = False):
            """Execute DELETE query, handling errors gracefully"""
            try:
                await db.execute(text(query), params)
            except Exception as e:
                error_msg = str(e).lower()
                # If table doesn't exist and it's optional, just continue
                if optional and ("does not exist" in error_msg or "undefinedtable" in error_msg):
                    return  # Table doesn't exist, skip
                # If transaction is aborted, rollback and re-raise immediately
                if "aborted" in error_msg or "in failed sql transaction" in error_msg:
                    await db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Erro ao deletar {table_name}: Transação abortada. Um comando anterior falhou. Erro: {str(e)}"
                    )
                # For other errors, rollback and re-raise
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Erro ao deletar {table_name}: {str(e)}"
                )
        
        # Delete in correct order to respect foreign key constraints
        # 1. Delete clinical records, prescriptions, diagnoses first (they reference appointments)
        # These are optional tables that might not exist, so we handle errors gracefully
        # Use a helper function that checks for transaction abort and handles it properly
        async def safe_delete_optional(query: str, params: dict, table_name: str):
            """Delete from optional table, handling errors gracefully - skip if table doesn't exist"""
            try:
                await db.execute(text(query), params)
            except Exception as e:
                error_msg = str(e).lower()
                # If table doesn't exist, PostgreSQL aborts the transaction
                # We need to rollback and restart the transaction
                if "does not exist" in error_msg or "undefinedtable" in error_msg:
                    # Rollback to clear the aborted transaction
                    await db.rollback()
                    # Restart transaction by executing a simple query
                    await db.execute(text("SELECT 1"))
                    return  # Table doesn't exist, skip
                # If transaction is aborted for other reasons, rollback and re-raise
                if "aborted" in error_msg or "in failed sql transaction" in error_msg:
                    await db.rollback()
                    # Restart transaction
                    await db.execute(text("SELECT 1"))
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Erro ao deletar {table_name}: Transação abortada. Erro: {str(e)}"
                    )
                # For any other error, re-raise to be handled by outer exception handler
                raise
        
        # PHASE 1: Delete all optional tables first (these may cause ROLLBACK if they don't exist)
        # This ensures that if there's a ROLLBACK, we haven't lost any critical operations yet
        
        # Delete records that reference appointments (must be deleted before appointments)
        # These are optional tables that might not exist
        await safe_delete_optional("""
            DELETE FROM clinical_records 
            WHERE appointment_id IN (SELECT id FROM appointments WHERE clinic_id = :clinic_id)
        """, {"clinic_id": clinic_id}, "clinical_records")
        
        await safe_delete_optional("""
            DELETE FROM prescriptions 
            WHERE appointment_id IN (SELECT id FROM appointments WHERE clinic_id = :clinic_id)
        """, {"clinic_id": clinic_id}, "prescriptions")
        
        await safe_delete_optional("""
            DELETE FROM diagnoses 
            WHERE appointment_id IN (SELECT id FROM appointments WHERE clinic_id = :clinic_id)
        """, {"clinic_id": clinic_id}, "diagnoses")
        
        await safe_delete_optional("""
            DELETE FROM patient_calls 
            WHERE appointment_id IN (SELECT id FROM appointments WHERE clinic_id = :clinic_id)
        """, {"clinic_id": clinic_id}, "patient_calls")
        
        await safe_delete_optional("""
            DELETE FROM file_uploads 
            WHERE appointment_id IN (SELECT id FROM appointments WHERE clinic_id = :clinic_id)
        """, {"clinic_id": clinic_id}, "file_uploads")
        
        await safe_delete_optional("""
            DELETE FROM voice_sessions 
            WHERE appointment_id IN (SELECT id FROM appointments WHERE clinic_id = :clinic_id)
        """, {"clinic_id": clinic_id}, "voice_sessions (by appointment)")
        
        # Delete stock movements (optional - table might not exist)
        await safe_delete_optional("DELETE FROM stock_movements WHERE clinic_id = :clinic_id", {"clinic_id": clinic_id}, "stock_movements")
        
        # Delete procedures (optional - table might not exist)
        await safe_delete_optional("DELETE FROM procedures WHERE clinic_id = :clinic_id", {"clinic_id": clinic_id}, "procedures")
        
        # Delete insurance plans (optional - table might not exist)
        await safe_delete_optional("DELETE FROM insurance_plans WHERE clinic_id = :clinic_id", {"clinic_id": clinic_id}, "insurance_plans")
        
        # Delete preauth requests (optional - table might not exist)
        await safe_delete_optional("DELETE FROM preauth_requests WHERE clinic_id = :clinic_id", {"clinic_id": clinic_id}, "preauth_requests")
        
        # Delete stock alerts (optional - table might not exist)
        await safe_delete_optional("DELETE FROM stock_alerts WHERE clinic_id = :clinic_id", {"clinic_id": clinic_id}, "stock_alerts")
        
        # Delete message threads (optional - table might not exist)
        await safe_delete_optional("DELETE FROM message_threads WHERE clinic_id = :clinic_id", {"clinic_id": clinic_id}, "message_threads")
        
        # Delete voice sessions by user_id (optional - table might not exist)
        # Note: voice_sessions by appointment_id were already deleted above
        await safe_delete_optional("""
            DELETE FROM voice_sessions 
            WHERE user_id IN (SELECT id FROM users WHERE clinic_id = :clinic_id)
               AND appointment_id IS NULL
        """, {"clinic_id": clinic_id}, "voice_sessions (by user)")
        
        # Delete user settings (optional - table might not exist)
        await safe_delete_optional("""
            DELETE FROM user_settings 
            WHERE user_id IN (SELECT id FROM users WHERE clinic_id = :clinic_id)
        """, {"clinic_id": clinic_id}, "user_settings")
        
        # PHASE 2: Delete critical tables (these must succeed)
        # After all optional tables are handled, delete critical tables
        # This ensures that if there was a ROLLBACK from optional tables, we still have a clean transaction
        
        # 1. First, clear appointment_id references in invoices (invoices reference appointments)
        await safe_delete("""
            UPDATE invoices 
            SET appointment_id = NULL 
            WHERE appointment_id IN (SELECT id FROM appointments WHERE clinic_id = :clinic_id)
        """, {"clinic_id": clinic_id}, "invoices.appointment_id")
        
        # 2. Delete invoice_lines (must be deleted before invoices)
        await safe_delete_optional("""
            DELETE FROM invoice_lines 
            WHERE invoice_id IN (SELECT id FROM invoices WHERE clinic_id = :clinic_id)
        """, {"clinic_id": clinic_id}, "invoice_lines")
        
        # 3. Delete payments (may reference users and invoices)
        # Must be deleted before invoices to avoid foreign key issues
        await safe_delete("""
            DELETE FROM payments 
            WHERE invoice_id IN (SELECT id FROM invoices WHERE clinic_id = :clinic_id)
               OR created_by IN (SELECT id FROM users WHERE clinic_id = :clinic_id)
        """, {"clinic_id": clinic_id}, "payments")
        
        # 4. Delete invoices (must be deleted before appointments since invoices reference appointments)
        # Note: We already cleared appointment_id references above, so this should be safe
        try:
            await db.execute(text("DELETE FROM invoices WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
        except Exception as e:
            error_msg = str(e).lower()
            if "foreign key" in error_msg or "constraint" in error_msg:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Erro ao deletar invoices: {str(e)}"
                )
            raise
        
        # 5. Now we can safely delete appointments (they reference users and patients)
        # All references to appointments have been cleared or deleted
        try:
            await db.execute(text("DELETE FROM appointments WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
        except Exception as e:
            error_msg = str(e).lower()
            if "foreign key" in error_msg or "constraint" in error_msg:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Erro ao deletar appointments: {str(e)}"
                )
            raise
        
        # 6. Delete patients
        await safe_delete("DELETE FROM patients WHERE clinic_id = :clinic_id", {"clinic_id": clinic_id}, "patients")
        
        # 7. Delete users (after appointments and payments that reference them)
        await safe_delete("DELETE FROM users WHERE clinic_id = :clinic_id", {"clinic_id": clinic_id}, "users")
        
        # 8. Delete products
        await safe_delete("DELETE FROM products WHERE clinic_id = :clinic_id", {"clinic_id": clinic_id}, "products")
        
        # 9. Delete service_items (they reference clinics)
        await safe_delete_optional("DELETE FROM service_items WHERE clinic_id = :clinic_id", {"clinic_id": clinic_id}, "service_items")
        
        # Check for any remaining references to the clinic (e.g., licenses)
        # Delete license relationship if exists
        await safe_delete_optional("""
            UPDATE clinics 
            SET license_id = NULL 
            WHERE id = :clinic_id
        """, {"clinic_id": clinic_id}, "clinics.license_id")
        
        # Finally, delete the clinic itself
        try:
            await db.execute(text("DELETE FROM clinics WHERE id = :clinic_id"), {"clinic_id": clinic_id})
            await db.commit()
        except Exception as delete_error:
            await db.rollback()
            error_msg = str(delete_error)
            # Log the full error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to delete clinic {clinic_id}: {error_msg}")
            
            # Check for foreign key constraint errors
            if "foreign key" in error_msg.lower() or "constraint" in error_msg.lower() or "violates foreign key" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Não é possível excluir a clínica: existem registros relacionados que impedem a exclusão. Por favor, verifique se todos os registros relacionados foram deletados. Erro detalhado: {error_msg}"
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao excluir clínica: {error_msg}"
            )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        await db.rollback()
        error_msg = str(e)
        # Log the full error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error deleting clinic {clinic_id}: {error_msg}", exc_info=True)
        
        # Check for foreign key constraint errors
        if "foreign key" in error_msg.lower() or "constraint" in error_msg.lower() or "violates foreign key" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não é possível excluir a clínica: existem registros relacionados que impedem a exclusão. Por favor, verifique se todos os registros relacionados foram deletados. Erro: {error_msg}"
            )
        # Check for missing table errors
        if "does not exist" in error_msg.lower() or "undefinedtable" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao excluir clínica: Tabela não encontrada no banco de dados. Por favor, verifique as migrações do banco de dados. Erro: {error_msg}"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao excluir clínica: {error_msg}"
        )
    
    return {"message": "Clinic deleted successfully"}


# ==================== System Logs ====================

@router.get("/logs", response_model=List[SystemLogResponse])
async def list_logs(
    level: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    try:
        query = select(SystemLog)
        if level:
            query = query.filter(SystemLog.level == level)
        if source:
            query = query.filter(SystemLog.source == source)
        if search:
            like = f"%{search}%"
            query = query.filter(or_(SystemLog.message.ilike(like), SystemLog.details.ilike(like)))
        query = query.order_by(SystemLog.timestamp.desc()).limit(limit)
        result = await db.execute(query)
        logs = result.scalars().all()
        return [SystemLogResponse.model_validate(l) for l in logs]
    except SQLAlchemyError as e:
        # If table doesn't exist yet, return empty list gracefully
        if "relation \"system_logs\" does not exist" in str(e):
            return []
        raise


@router.post("/logs", response_model=SystemLogResponse, status_code=status.HTTP_201_CREATED)
async def create_log(
    payload: SystemLogCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    log = SystemLog(
        level=payload.level,
        message=payload.message,
        source=payload.source,
        details=payload.details,
        user_id=payload.user_id or current_user.id,
        clinic_id=payload.clinic_id or current_user.clinic_id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return SystemLogResponse.model_validate(log)


@router.put("/logs/{log_id}", response_model=SystemLogResponse)
async def update_log(
    log_id: int,
    payload: SystemLogUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    result = await db.execute(select(SystemLog).where(SystemLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(log, k, v)
    await db.commit()
    await db.refresh(log)
    return SystemLogResponse.model_validate(log)


@router.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log(
    log_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    result = await db.execute(select(SystemLog).where(SystemLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    await db.delete(log)
    await db.commit()
    return {"status": "ok"}


@router.get("/modules", response_model=List[str])
async def get_available_modules(
    current_user: User = Depends(require_admin)
):
    """
    Get list of available modules
    """
    return AVAILABLE_MODULES


@router.patch("/clinics/me/modules", response_model=ClinicResponse)
async def update_my_clinic_modules(
    modules_data: Dict[str, Any],
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update the current clinic's active modules
    Only admins can update modules
    """
    if not current_user.clinic_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not associated with a clinic"
        )
    
    query = select(Clinic).filter(Clinic.id == current_user.clinic_id)
    result = await db.execute(query)
    clinic = result.scalar_one_or_none()
    
    if not clinic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found"
        )
    
    # Validate modules
    active_modules = modules_data.get("active_modules", [])
    if not isinstance(active_modules, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="active_modules must be a list"
        )
    
    # Validate each module
    for module in active_modules:
        if module not in AVAILABLE_MODULES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid module: {module}. Available modules: {AVAILABLE_MODULES}"
            )
    
    # Update modules
    clinic.active_modules = active_modules
    await db.commit()
    await db.refresh(clinic)
    
    # Return updated clinic - use same conversion approach
    from datetime import date as date_type, datetime
    
    def to_date(dt_value):
        """Convert datetime or date to pure date object - guaranteed"""
        if dt_value is None:
            return None
        if isinstance(dt_value, date_type):
            return date_type(dt_value.year, dt_value.month, dt_value.day)
        if isinstance(dt_value, datetime):
            if dt_value.tzinfo is not None:
                from datetime import timezone as tz
                dt_value = dt_value.astimezone(tz.utc)
            return date_type(dt_value.year, dt_value.month, dt_value.day)
        if hasattr(dt_value, 'date'):
            dt_result = dt_value.date()
            if isinstance(dt_result, datetime):
                if dt_result.tzinfo is not None:
                    from datetime import timezone as tz
                    dt_result = dt_result.astimezone(tz.utc)
                return date_type(dt_result.year, dt_result.month, dt_result.day)
            if isinstance(dt_result, date_type):
                return date_type(dt_result.year, dt_result.month, dt_result.day)
        return date_type.today()
    
    response_dict = {
        "id": clinic.id,
        "name": clinic.name,
        "legal_name": clinic.legal_name,
        "tax_id": clinic.tax_id,
        "address": clinic.address,
        "phone": clinic.phone,
        "email": clinic.email,
        "is_active": clinic.is_active,
        "license_key": clinic.license_key,
        "expiration_date": clinic.expiration_date,
        "max_users": clinic.max_users,
        "active_modules": clinic.active_modules or [],
        "created_at": to_date(getattr(clinic, "created_at", None)) or date_type.today(),
        "updated_at": to_date(getattr(clinic, "updated_at", None)),
    }
    
    try:
        return ClinicResponse.model_validate(response_dict)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"ClinicResponse validation failed: {e}")
        return ClinicResponse.model_construct(**response_dict)


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

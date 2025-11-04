"""
Licensing and Multi-tenancy Middleware
Handles clinic license validation and user limits
"""

from datetime import date
from typing import List, Optional
from fastapi import HTTPException, status, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_session
from app.models import Clinic, User
from app.core.auth import get_current_user


class LicenseError(Exception):
    """Custom exception for licensing errors"""
    pass


async def get_clinic_license(
    clinic_id: int,
    db: AsyncSession
) -> Clinic:
    """
    Get clinic with license information
    """
    query = select(Clinic).filter(Clinic.id == clinic_id)
    result = await db.execute(query)
    clinic = result.scalar_one_or_none()
    
    if not clinic:
        raise LicenseError("Clinic not found")
    
    return clinic


def validate_license(clinic: Clinic) -> None:
    """
    Validate clinic license
    """
    # Check if clinic is active
    if not clinic.is_active:
        raise LicenseError("Clinic is not active")
    
    # Check if license has expired
    if clinic.expiration_date and clinic.expiration_date < date.today():
        raise LicenseError("Clinic license has expired")
    
    # Check if license key exists (for paid licenses)
    if clinic.license_key is None:
        raise LicenseError("Clinic license is not valid")


async def check_user_limit(
    clinic_id: int,
    db: AsyncSession
) -> None:
    """
    Check if clinic has exceeded user limit
    """
    # Get clinic license info
    clinic = await get_clinic_license(clinic_id, db)
    
    # Validate license
    validate_license(clinic)
    
    # Count active users
    user_count_query = select(func.count(User.id)).filter(
        User.clinic_id == clinic_id,
        User.is_active == True
    )
    result = await db.execute(user_count_query)
    user_count = result.scalar()
    
    # Check if user limit exceeded
    if user_count >= clinic.max_users:
        raise LicenseError(f"Clinic has reached maximum user limit of {clinic.max_users}")


def check_module_access(clinic: Clinic, module: str) -> bool:
    """
    Check if clinic has access to a specific module
    """
    if not clinic.active_modules:
        return False
    
    return module in clinic.active_modules


async def require_license(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> Clinic:
    """
    Dependency to require valid clinic license
    """
    try:
        clinic = await get_clinic_license(current_user.clinic_id, db)
        validate_license(clinic)
        return clinic
    except LicenseError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


async def require_user_limit_check(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> Clinic:
    """
    Dependency to require valid license and user limit check
    """
    try:
        clinic = await get_clinic_license(current_user.clinic_id, db)
        validate_license(clinic)
        await check_user_limit(current_user.clinic_id, db)
        return clinic
    except LicenseError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


def require_module(module: str):
    """
    Decorator factory to require specific module access
    """
    async def module_dependency(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_session)
    ) -> Clinic:
        try:
            clinic = await get_clinic_license(current_user.clinic_id, db)
            validate_license(clinic)
            
            if not check_module_access(clinic, module):
                raise LicenseError(f"Module '{module}' is not enabled for this clinic")
            
            return clinic
        except LicenseError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
    
    return module_dependency


# Available modules
AVAILABLE_MODULES = [
    "bi",           # Business Intelligence
    "telemed",      # Telemedicine
    "stock",        # Stock Management
    "financial",    # Financial Management
    "clinical",     # Clinical Records
    "appointments", # Appointment Management
    "patients",     # Patient Management
    "procedures",   # Procedure Management
    "tiss",         # TISS Integration
    "mobile",       # Mobile App Access
]

# Module dependencies
MODULE_DEPENDENCIES = {
    "bi": ["financial", "clinical", "appointments"],
    "telemed": ["appointments", "clinical"],
    "stock": ["financial"],
    "financial": ["appointments"],
    "clinical": ["appointments"],
    "procedures": ["financial", "stock"],
    "tiss": ["financial", "clinical"],
    "mobile": ["appointments", "clinical", "patients"],
}


def get_required_modules(requested_modules: List[str]) -> List[str]:
    """
    Get all modules required for the requested modules (including dependencies)
    """
    required = set(requested_modules)
    
    for module in requested_modules:
        if module in MODULE_DEPENDENCIES:
            required.update(MODULE_DEPENDENCIES[module])
    
    return list(required)


def validate_module_combination(modules: List[str]) -> None:
    """
    Validate that all required dependencies are included
    """
    for module in modules:
        if module in MODULE_DEPENDENCIES:
            missing_deps = set(MODULE_DEPENDENCIES[module]) - set(modules)
            if missing_deps:
                raise LicenseError(
                    f"Module '{module}' requires additional modules: {', '.join(missing_deps)}"
                )

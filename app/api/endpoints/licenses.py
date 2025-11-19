"""
Licensing API Endpoints
"""

import uuid
import json
import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from app.models import License, Activation, Entitlement, Clinic, User, AppointmentStatus
from app.models.license import LicenseStatus
from app.schemas.license import LicenseCreate, LicenseResponse, LicenseUpdate, LicenseListResponse
from app.schemas.activation import ActivationResponse
from app.schemas.entitlement import EntitlementListResponse
from app.core.auth import create_access_token, get_current_user
from app.core.validators import sanitize_input
from app.core.logging import security_logger

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, PublicFormat


router = APIRouter(prefix="/licenses", tags=["Licensing"])


# Simple in-memory keypair for signing/verification if none configured
_RSA_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_RSA_PUBLIC_KEY = _RSA_PRIVATE_KEY.public_key()


def _sign_payload(payload: Dict[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = _RSA_PRIVATE_KEY.sign(
        data,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return signature.hex()


def _verify_signature(payload: Dict[str, Any], signature_hex: str) -> bool:
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    try:
        _RSA_PUBLIC_KEY.verify(bytes.fromhex(signature_hex), data, padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False


def _compute_instance_id(tenant_tax_id: str, admin_email: str, fingerprint: Optional[str] = None) -> str:
    base = fingerprint or f"{tenant_tax_id}:{admin_email}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


async def _ensure_superadmin(user: User, db: AsyncSession):
    """Check if user is SuperAdmin by role_id or role_name"""
    # Check by role_id (SuperAdmin role_id is 1)
    if user.role_id == 1:
        return True
    
    # Check by role_name if user_role relationship is loaded
    if hasattr(user, 'user_role') and user.user_role:
        if user.user_role.name == "SuperAdmin":
            return True
    
    # Load user_role relationship if not already loaded
    if user.role_id:
        from app.models.menu import UserRole as UserRoleModel
        role_query = await db.execute(
            select(UserRoleModel).where(UserRoleModel.id == user.role_id)
        )
        role = role_query.scalar_one_or_none()
        if role and role.name == "SuperAdmin":
            return True
    
    # Fallback: require role admin and username == 'superadmin'
    if user.role.value.lower() == "admin" and user.username.lower() == "superadmin":
        return True
    
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SuperAdmin required")


@router.post("", response_model=LicenseResponse, status_code=status.HTTP_201_CREATED)
async def create_license(body: LicenseCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Create a new license (SuperAdmin only). Generates activation_key and digital signature.
    Initial status will be set to 'suspended' to represent inactive until activation.
    """
    await _ensure_superadmin(current_user, db)

    # Validate clinic exists
    clinic_q = await db.execute(select(Clinic).where(Clinic.id == body.tenant_id))
    clinic = clinic_q.scalar_one_or_none()
    if not clinic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant clinic not found")

    # Check if clinic already has a license
    if clinic.license_id:
        existing_license_q = await db.execute(select(License).where(License.id == clinic.license_id))
        existing_license = existing_license_q.scalar_one_or_none()
        if existing_license and existing_license.status != LicenseStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Clinic already has an active license. Please cancel the existing license first."
            )

    # Build payload to sign
    payload = {
        "tenant_id": str(body.tenant_id),
        "plan": body.plan.value if hasattr(body.plan, "value") else str(body.plan),
        "modules": body.modules,
        "users_limit": body.users_limit,
        "units_limit": body.units_limit,
        "start_at": int(body.start_at.replace(tzinfo=timezone.utc).timestamp()),
        "end_at": int(body.end_at.replace(tzinfo=timezone.utc).timestamp()),
    }
    signature = _sign_payload(payload)

    # Calculate AI token limit if not provided
    ai_token_limit = body.ai_token_limit
    if ai_token_limit is None:
        # Set default based on plan
        plan_str = payload["plan"].lower() if isinstance(payload["plan"], str) else str(payload["plan"]).lower()
        if plan_str == "basic":
            ai_token_limit = 10_000
        elif plan_str == "professional":
            ai_token_limit = 100_000
        elif plan_str == "enterprise":
            ai_token_limit = 1_000_000
        elif plan_str == "custom":
            ai_token_limit = -1  # Unlimited
        else:
            ai_token_limit = 0  # Disabled by default
    
    # Determine if AI is enabled (check if "ai" is in modules or ai_enabled is True)
    ai_enabled = body.ai_enabled or ("ai" in body.modules)
    
    try:
        # Create license
        license_obj = License(
            tenant_id=clinic.id,
            plan=payload["plan"],
            modules=body.modules,
            users_limit=body.users_limit,
            units_limit=body.units_limit,
            start_at=body.start_at,
            end_at=body.end_at,
            status=LicenseStatus.SUSPENDED,
            signature=signature,
            ai_token_limit=ai_token_limit,
            ai_enabled=ai_enabled,
        )

        db.add(license_obj)
        await db.flush()  # Flush to get license.id and activation_key without committing
        await db.refresh(license_obj)
        
        # Note: get_db dependency will commit automatically at the end of the function
        # But we need to ensure the license is persisted before returning
        # The flush() above ensures the license gets an ID, and the commit will happen
        # automatically when the function returns successfully

        # Log the creation (non-blocking)
        try:
            security_logger.log_security_event(
                event_type="license_created",
                user_id=current_user.id,
                username=current_user.username,
                ip_address=None,
                description=f"License created for tenant {clinic.id}",
                severity="INFO",
                additional_data={"license_id": str(license_obj.id)}
            )
        except Exception as log_error:
            # Don't fail license creation if logging fails
            print(f"Warning: Failed to log license creation: {log_error}")

        return LicenseResponse.model_validate(license_obj)
    except Exception as e:
        await db.rollback()
        error_msg = str(e)
        
        # Check for unique constraint violations
        if "unique" in error_msg.lower() or "duplicate" in error_msg.lower() or "violates unique constraint" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"License creation failed: Duplicate entry. {error_msg}"
            )
        
        # Check for foreign key constraint errors
        if "foreign key" in error_msg.lower() or "constraint" in error_msg.lower() or "violates foreign key" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"License creation failed: Invalid clinic reference. {error_msg}"
            )
        
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating license: {error_msg}", exc_info=True)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar licença: {error_msg}"
        )


class ActivationRequestPublic:
    activation_key: uuid.UUID
    tenant_tax_id: str
    admin_email: str
    device_info: Optional[Dict[str, Any]]


@router.post("/activate")
async def activate_license(
    activation_key: str,
    tenant_tax_id: str,
    admin_email: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Public activation endpoint. Validates signature, creates Activation, links clinic to license,
    returns entitlements and JWT token for admin context.
    """
    activation_key = str(activation_key)
    tenant_tax_id = sanitize_input(tenant_tax_id, max_length=32)
    admin_email = sanitize_input(admin_email, max_length=100)

    # Find clinic by tax_id
    clinic_q = await db.execute(select(Clinic).where(Clinic.tax_id == tenant_tax_id))
    clinic = clinic_q.scalar_one_or_none()
    if not clinic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")

    # Find license by activation_key
    lic_q = await db.execute(select(License).where(License.activation_key == uuid.UUID(activation_key)))
    license_obj = lic_q.scalar_one_or_none()
    if not license_obj or license_obj.tenant_id != clinic.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found for this clinic")

    # Validate signature over core payload
    payload = {
        "tenant_id": str(license_obj.tenant_id),
        "plan": license_obj.plan,
        "modules": license_obj.modules,
        "users_limit": license_obj.users_limit,
        "units_limit": license_obj.units_limit,
        "start_at": int(license_obj.start_at.replace(tzinfo=timezone.utc).timestamp()),
        "end_at": int(license_obj.end_at.replace(tzinfo=timezone.utc).timestamp()),
    }
    if not license_obj.signature or not _verify_signature(payload, license_obj.signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid license signature")

    # Compute instance_id (no device info in spec, derive from identifiers)
    instance_id = _compute_instance_id(tenant_tax_id, admin_email)

    # Create activation
    activation = Activation(
        license_id=license_obj.id,
        instance_id=instance_id,
        device_info={"tenant_tax_id": tenant_tax_id, "admin_email": admin_email},
    )
    db.add(activation)

    # Link clinic to license if not already
    if clinic.license_id != license_obj.id:
        clinic.license_id = license_obj.id
        db.add(clinic)

    # Optionally set license active
    license_obj.status = LicenseStatus.ACTIVE
    db.add(license_obj)

    await db.flush()
    await db.refresh(activation)

    # Build entitlements
    ent_q = await db.execute(select(Entitlement).where(Entitlement.license_id == license_obj.id))
    ents: List[Entitlement] = ent_q.scalars().all()
    entitlements = [
        {
            "module": e.module,
            "enabled": e.enabled,
            "limits": e.limits_json or {},
        }
        for e in ents
    ]

    # Issue JWT token for admin context (short-lived activation token)
    token_data = {
        "tenant_id": clinic.id,
        "clinic_id": clinic.id,
        "scope": "license_activation",
    }
    access_token = create_access_token(data=token_data, expires_delta=timedelta(minutes=15))

    security_logger.log_security_event(
        event_type="license_activated",
        user_id=None,
        username=None,
        ip_address=None,
        description=f"License activated for tenant {clinic.id}",
        severity="INFO",
        additional_data={"license_id": str(license_obj.id), "activation_id": str(activation.id)}
    )

    return {
        "success": True,
        "license_id": str(license_obj.id),
        "activation_id": str(activation.id),
        "entitlements": entitlements,
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 900,
    }


@router.get("", response_model=List[LicenseResponse])
async def list_licenses(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all licenses (SuperAdmin only)
    """
    await _ensure_superadmin(current_user, db)
    
    licenses_q = await db.execute(
        select(License, Clinic)
        .join(Clinic, License.tenant_id == Clinic.id)
        .order_by(License.created_at.desc())
    )
    results = licenses_q.all()
    
    licenses_list = []
    for license_obj, clinic in results:
        license_dict = LicenseResponse.model_validate(license_obj).model_dump()
        license_dict['clinic_name'] = clinic.name
        licenses_list.append(license_dict)
    
    return licenses_list


@router.get("/me")
async def get_my_license(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current clinic's license information
    Returns license details for the authenticated user's clinic
    """
    if not current_user.clinic_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not associated with a clinic"
        )
    
    # Fetch clinic
    clinic_q = await db.execute(select(Clinic).where(Clinic.id == current_user.clinic_id))
    clinic = clinic_q.scalar_one_or_none()
    
    if not clinic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found"
        )
    
    # Try to get new license system (via license_id)
    license_obj = None
    if clinic.license_id:
        license_q = await db.execute(select(License).where(License.id == clinic.license_id))
        license_obj = license_q.scalar_one_or_none()
    
    # Build response with both new and legacy license info
    response = {
        "has_license": license_obj is not None or clinic.license_key is not None,
        "license_type": None,
        "status": None,
        "expiration_date": None,
        "max_users": clinic.max_users or 0,
        "license_key": clinic.license_key or None,
    }
    
    if license_obj:
        # New license system
        response.update({
            "license_id": str(license_obj.id),
            "license_type": license_obj.plan,
            "status": license_obj.status.value,
            "expiration_date": license_obj.end_at.isoformat() if license_obj.end_at else None,
            "max_users": license_obj.users_limit,
            "start_date": license_obj.start_at.isoformat() if license_obj.start_at else None,
            "activation_key": str(license_obj.activation_key) if license_obj.activation_key else None,
            "is_active": license_obj.is_active,
            "days_until_expiry": license_obj.days_until_expiry,
            "modules": license_obj.modules or [],
        })
    elif clinic.license_key:
        # Legacy license system
        response.update({
            "license_type": "Legacy",
            "status": "active" if (clinic.expiration_date and clinic.expiration_date >= datetime.now(timezone.utc).date()) else "expired",
            "expiration_date": clinic.expiration_date.isoformat() if clinic.expiration_date else None,
            "license_key": clinic.license_key,
        })
    else:
        # No license
        response.update({
            "status": "none",
            "license_type": "Nenhuma",
        })
    
    return response


@router.get("/entitlements")
async def get_entitlements(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Fetch clinic
    clinic_q = await db.execute(select(Clinic).where(Clinic.id == current_user.clinic_id))
    clinic = clinic_q.scalar_one_or_none()
    if not clinic or not clinic.license_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No license for current tenant")

    ent_q = await db.execute(select(Entitlement).where(Entitlement.license_id == clinic.license_id))
    ents: List[Entitlement] = ent_q.scalars().all()
    return [
        {
            "module": e.module,
            "enabled": e.enabled,
            "limits": e.limits_json or {},
        }
        for e in ents
    ]


@router.get("/{license_id}", response_model=LicenseResponse)
async def get_license(
    license_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific license by ID (SuperAdmin only)
    """
    await _ensure_superadmin(current_user, db)
    
    license_q = await db.execute(select(License).where(License.id == license_id))
    license_obj = license_q.scalar_one_or_none()
    
    if not license_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    
    return LicenseResponse.model_validate(license_obj)


@router.put("/{license_id}", response_model=LicenseResponse)
async def update_license(
    license_id: uuid.UUID,
    license_update: LicenseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a license (SuperAdmin only)
    """
    await _ensure_superadmin(current_user, db)
    
    license_q = await db.execute(select(License).where(License.id == license_id))
    license_obj = license_q.scalar_one_or_none()
    
    if not license_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    
    # Update fields
    update_data = license_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(license_obj, field, value)
    
    # Re-sign if core fields changed
    if any(field in update_data for field in ['plan', 'modules', 'users_limit', 'units_limit', 'start_at', 'end_at']):
        payload = {
            "tenant_id": str(license_obj.tenant_id),
            "plan": license_obj.plan if isinstance(license_obj.plan, str) else license_obj.plan.value,
            "modules": license_obj.modules,
            "users_limit": license_obj.users_limit,
            "units_limit": license_obj.units_limit,
            "start_at": int(license_obj.start_at.replace(tzinfo=timezone.utc).timestamp()),
            "end_at": int(license_obj.end_at.replace(tzinfo=timezone.utc).timestamp()),
        }
        license_obj.signature = _sign_payload(payload)
    
    await db.commit()
    await db.refresh(license_obj)
    
    return LicenseResponse.model_validate(license_obj)


@router.delete("/{license_id}")
async def delete_license(
    license_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a license (SuperAdmin only) - sets status to CANCELLED
    """
    await _ensure_superadmin(current_user, db)
    
    license_q = await db.execute(select(License).where(License.id == license_id))
    license_obj = license_q.scalar_one_or_none()
    
    if not license_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    
    license_obj.status = LicenseStatus.CANCELLED
    await db.commit()
    
    return {"message": "License cancelled successfully"}



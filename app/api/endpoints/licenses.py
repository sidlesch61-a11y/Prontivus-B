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
from app.schemas.license import LicenseCreate, LicenseResponse
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


def _ensure_superadmin(user: User):
    if user.role.value.lower() != "admin" and getattr(user, "is_superadmin", False) is not True:
        # Fallback: require role admin and username == 'superadmin' if no flag
        if user.username.lower() != "superadmin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SuperAdmin required")


@router.post("", response_model=LicenseResponse, status_code=status.HTTP_201_CREATED)
async def create_license(body: LicenseCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Create a new license (SuperAdmin only). Generates activation_key and digital signature.
    Initial status will be set to 'suspended' to represent inactive until activation.
    """
    _ensure_superadmin(current_user)

    # Validate clinic exists
    clinic_q = await db.execute(select(Clinic).where(Clinic.id == body.tenant_id))
    clinic = clinic_q.scalar_one_or_none()
    if not clinic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant clinic not found")

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
    )

    db.add(license_obj)
    await db.flush()
    await db.refresh(license_obj)

    security_logger.log_security_event(
        event_type="license_created",
        user_id=current_user.id,
        username=current_user.username,
        ip_address=None,
        description=f"License created for tenant {clinic.id}",
        severity="INFO",
        additional_data={"license_id": str(license_obj.id)}
    )

    return LicenseResponse.model_validate(license_obj)


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



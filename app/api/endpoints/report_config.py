"""
Report Configuration Endpoints
Stores and retrieves per-clinic report configuration settings
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError, ProgrammingError
from typing import Any, Dict

from app.core.auth import get_current_user, RoleChecker
from database import get_async_session
from app.models import User, UserRole
from app.models.report_config import ReportConfig

# Require admin role for update operations
require_admin = RoleChecker([UserRole.ADMIN])

router = APIRouter(prefix="/report-config", tags=["Report Config"])


def _defaults():
    """Return default report configuration"""
    return {
        "financial": {
            "enabled": True,
            "detailed": True
        },
        "clinical": {
            "enabled": True,
            "anonymize": False
        },
        "operational": {
            "enabled": True,
            "automatic_scheduling": False
        },
        "general": {
            "allow_export": True,
            "send_by_email": False
        }
    }


@router.get("")
async def get_report_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get report configuration for the current clinic
    Returns default configuration if none exists
    """
    try:
        result = await db.execute(
            select(ReportConfig).where(ReportConfig.clinic_id == current_user.clinic_id)
        )
        cfg = result.scalar_one_or_none()
        if not cfg:
            return _defaults()
        return {
            "financial": cfg.financial or _defaults()["financial"],
            "clinical": cfg.clinical or _defaults()["clinical"],
            "operational": cfg.operational or _defaults()["operational"],
            "general": cfg.general or _defaults()["general"],
        }
    except (ProgrammingError, SQLAlchemyError):
        # Table may not exist yet on new environments; return defaults instead of 500
        return _defaults()


@router.put("")
async def upsert_report_config(
    payload: Dict[str, Any],
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create or update report configuration for the current clinic
    Only admins can update report configurations
    """
    try:
        result = await db.execute(
            select(ReportConfig).where(ReportConfig.clinic_id == current_user.clinic_id)
        )
        cfg = result.scalar_one_or_none()
        
        defaults = _defaults()
        
        if not cfg:
            cfg = ReportConfig(
                clinic_id=current_user.clinic_id,
                financial=payload.get("financial", defaults["financial"]),
                clinical=payload.get("clinical", defaults["clinical"]),
                operational=payload.get("operational", defaults["operational"]),
                general=payload.get("general", defaults["general"]),
            )
            db.add(cfg)
        else:
            if "financial" in payload:
                cfg.financial = payload["financial"]
            if "clinical" in payload:
                cfg.clinical = payload["clinical"]
            if "operational" in payload:
                cfg.operational = payload["operational"]
            if "general" in payload:
                cfg.general = payload["general"]

        await db.commit()
        await db.refresh(cfg)
        
        return {
            "message": "Report configuration saved successfully",
            "config": {
                "financial": cfg.financial,
                "clinical": cfg.clinical,
                "operational": cfg.operational,
                "general": cfg.general,
            }
        }
    except (ProgrammingError, SQLAlchemyError) as e:
        await db.rollback()
        # Surface a friendly error if table is missing; frontend can guide to run migrations
        raise HTTPException(
            status_code=500,
            detail="Report config storage not initialized. Run migrations."
        )


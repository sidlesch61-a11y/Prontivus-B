"""
TISS Configuration Endpoints
Stores and retrieves per-clinic TISS configuration
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError, ProgrammingError
from typing import Any, Dict, Optional

from app.core.auth import get_current_user
from app.middleware.permissions import require_super_admin
from database import get_async_session
from app.models import User
from app.models.tiss_config import TissConfig

router = APIRouter(prefix="/tiss-config", tags=["TISS Config"])


def _defaults():
    return {
        "prestador": {"cnpj": "", "nome": "", "codigo_prestador": "001"},
        "operadora": {"cnpj": "", "nome": "Operadora Padrão", "registro_ans": "000000"},
        "defaults": {"nome_plano": "Plano Padrão", "cbo_profissional": "2251", "hora_inicio": "08:00", "hora_fim": "09:00"},
        "tiss": {"versao": "3.03.00", "enabled": True, "auto_generate": False},
    }


@router.get("")
async def get_tiss_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    try:
        result = await db.execute(select(TissConfig).where(TissConfig.clinic_id == current_user.clinic_id))
        cfg = result.scalar_one_or_none()
        if not cfg:
            return _defaults()
        return {
            "prestador": cfg.prestador or {},
            "operadora": cfg.operadora or {},
            "defaults": cfg.defaults or {},
            "tiss": cfg.tiss or {},
        }
    except (ProgrammingError, SQLAlchemyError):
        # Table may not exist yet on new environments; return defaults instead of 500
        return _defaults()


@router.put("")
async def upsert_tiss_config(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    try:
        if not current_user.clinic_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not associated with a clinic"
            )
        
        result = await db.execute(select(TissConfig).where(TissConfig.clinic_id == current_user.clinic_id))
        cfg = result.scalar_one_or_none()
        if not cfg:
            cfg = TissConfig(
                clinic_id=current_user.clinic_id,
                prestador=payload.get("prestador", {}),
                operadora=payload.get("operadora", {}),
                defaults=payload.get("defaults", {}),
                tiss=payload.get("tiss", {}),
            )
            db.add(cfg)
        else:
            if "prestador" in payload:
                cfg.prestador = payload.get("prestador", {})
            if "operadora" in payload:
                cfg.operadora = payload.get("operadora", {})
            if "defaults" in payload:
                cfg.defaults = payload.get("defaults", {})
            if "tiss" in payload:
                cfg.tiss = payload.get("tiss", {})

        await db.commit()
        await db.refresh(cfg)
        return {"message": "TISS config saved"}
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except (ProgrammingError, SQLAlchemyError) as e:
        await db.rollback()
        error_msg = str(e).lower()
        # Check if table doesn't exist
        if "does not exist" in error_msg or "undefinedtable" in error_msg or "relation" in error_msg:
            raise HTTPException(
                status_code=500, 
                detail="TISS config storage not initialized. Run migrations: alembic upgrade head"
            )
        # For other database errors, return a generic message
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Database error saving TISS config: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error saving TISS config: {str(e)}"
        )
    except Exception as e:
        await db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error saving TISS config: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error saving TISS config: {str(e)}"
        )


@router.get("/admin/{clinic_id}")
async def get_tiss_config_for_clinic(
    clinic_id: int,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get TISS config for a specific clinic (SuperAdmin only)
    """
    try:
        result = await db.execute(select(TissConfig).where(TissConfig.clinic_id == clinic_id))
        cfg = result.scalar_one_or_none()
        if not cfg:
            return _defaults()
        return {
            "prestador": cfg.prestador or {},
            "operadora": cfg.operadora or {},
            "defaults": cfg.defaults or {},
            "tiss": cfg.tiss or {},
        }
    except (ProgrammingError, SQLAlchemyError):
        return _defaults()


@router.put("/admin/{clinic_id}")
async def upsert_tiss_config_for_clinic(
    clinic_id: int,
    payload: Dict[str, Any],
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update TISS config for a specific clinic (SuperAdmin only)
    """
    try:
        # Validate clinic exists
        from app.models import Clinic
        clinic_result = await db.execute(select(Clinic).where(Clinic.id == clinic_id))
        clinic = clinic_result.scalar_one_or_none()
        if not clinic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Clinic with id {clinic_id} not found"
            )
        
        result = await db.execute(select(TissConfig).where(TissConfig.clinic_id == clinic_id))
        cfg = result.scalar_one_or_none()
        if not cfg:
            cfg = TissConfig(
                clinic_id=clinic_id,
                prestador=payload.get("prestador", {}),
                operadora=payload.get("operadora", {}),
                defaults=payload.get("defaults", {}),
                tiss=payload.get("tiss", {}),
            )
            db.add(cfg)
        else:
            if "prestador" in payload:
                cfg.prestador = payload.get("prestador", {})
            if "operadora" in payload:
                cfg.operadora = payload.get("operadora", {})
            if "defaults" in payload:
                cfg.defaults = payload.get("defaults", {})
            if "tiss" in payload:
                cfg.tiss = payload.get("tiss", {})

        await db.commit()
        await db.refresh(cfg)
        return {"message": "TISS config saved"}
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except (ProgrammingError, SQLAlchemyError) as e:
        await db.rollback()
        error_msg = str(e).lower()
        # Check if table doesn't exist
        if "does not exist" in error_msg or "undefinedtable" in error_msg or "relation" in error_msg:
            raise HTTPException(
                status_code=500, 
                detail="TISS config storage not initialized. Run migrations: alembic upgrade head"
            )
        # For other database errors, return a generic message
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Database error saving TISS config: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error saving TISS config: {str(e)}"
        )
    except Exception as e:
        await db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error saving TISS config: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error saving TISS config: {str(e)}"
        )



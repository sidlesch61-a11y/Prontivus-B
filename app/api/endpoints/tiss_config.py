"""
TISS Configuration Endpoints
Stores and retrieves per-clinic TISS configuration
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Any, Dict

from app.core.auth import get_current_user
from database import get_async_session
from app.models import User
from app.models.tiss_config import TissConfig

router = APIRouter(prefix="/tiss-config", tags=["TISS Config"])


@router.get("")
async def get_tiss_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    result = await db.execute(select(TissConfig).where(TissConfig.clinic_id == current_user.clinic_id))
    cfg = result.scalar_one_or_none()
    if not cfg:
        # Return sensible defaults if not configured yet
        return {
            "prestador": {"cnpj": "", "nome": "", "codigo_prestador": "001"},
            "operadora": {"cnpj": "", "nome": "Operadora Padrão", "registro_ans": "000000"},
            "defaults": {"nome_plano": "Plano Padrão", "cbo_profissional": "2251", "hora_inicio": "08:00", "hora_fim": "09:00"},
            "tiss": {"versao": "3.03.00", "enabled": True, "auto_generate": False},
        }
    return {
        "prestador": cfg.prestador or {},
        "operadora": cfg.operadora or {},
        "defaults": cfg.defaults or {},
        "tiss": cfg.tiss or {},
    }


@router.put("")
async def upsert_tiss_config(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
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
            cfg.prestador = payload["prestador"]
        if "operadora" in payload:
            cfg.operadora = payload["operadora"]
        if "defaults" in payload:
            cfg.defaults = payload["defaults"]
        if "tiss" in payload:
            cfg.tiss = payload["tiss"]

    await db.commit()
    return {"message": "TISS config saved"}



"""
AI Configuration API Endpoints
Handles AI integration settings per clinic with token usage tracking
"""

from typing import Optional, Dict, Any
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Body, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from database import get_async_session
from app.core.auth import get_current_user
from app.models import User, AIConfig, License, Clinic
from app.middleware.permissions import require_super_admin, require_admin
from app.services.encryption_service import encrypt, decrypt
from app.services.ai_service import create_ai_service, AIServiceError

router = APIRouter(prefix="/ai-config", tags=["AI Configuration"])


def _default_ai_config() -> Dict[str, Any]:
    """Default AI configuration"""
    return {
        "enabled": False,
        "provider": "openai",
        "api_key": "",
        "model": "gpt-4",
        "base_url": "",
        "max_tokens": 2000,
        "temperature": 0.7,
        "features": {
            "clinical_analysis": {
                "enabled": False,
                "description": "Análise automática de prontuários médicos"
            },
            "diagnosis_suggestions": {
                "enabled": False,
                "description": "Sugestões baseadas em sintomas e histórico"
            },
            "predictive_analysis": {
                "enabled": False,
                "description": "Previsões baseadas em dados históricos"
            },
            "virtual_assistant": {
                "enabled": False,
                "description": "Assistente inteligente para médicos"
            }
        },
        "usage_stats": {
            "total_tokens": 0,
            "tokens_this_month": 0,
            "tokens_this_year": 0,
            "requests_count": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "last_reset_date": None,
            "last_request_date": None,
            "average_response_time_ms": 0,
            "documents_processed": 0,
            "suggestions_generated": 0,
            "approval_rate": 0.0
        }
    }


def _get_token_limit_by_plan(plan: str) -> int:
    """
    Get token limit per month based on license plan
    
    Returns:
        Token limit (0 = disabled, -1 = unlimited)
    """
    limits = {
        "basic": 10_000,  # 10k tokens/month
        "professional": 100_000,  # 100k tokens/month
        "enterprise": 1_000_000,  # 1M tokens/month
        "custom": -1  # Unlimited
    }
    return limits.get(plan.lower(), 0)


async def _get_clinic_license(db: AsyncSession, clinic_id: int, check_ai_module: bool = True) -> Optional[License]:
    """Get clinic's license with optional AI module check"""
    from app.models import Clinic
    
    result = await db.execute(
        select(Clinic)
        .where(Clinic.id == clinic_id)
        .options(selectinload(Clinic.license))
    )
    clinic = result.scalar_one_or_none()
    
    if not clinic or not clinic.license:
        return None
    
    license_obj = clinic.license
    
    # Check if AI module is enabled (only if check_ai_module is True)
    if check_ai_module:
        if "ai" not in license_obj.modules and "api" not in license_obj.modules:
            return None
    
    return license_obj


async def _get_or_create_ai_config(
    db: AsyncSession,
    clinic_id: int
) -> AIConfig:
    """Get existing AI config or create default one"""
    result = await db.execute(
        select(AIConfig).where(AIConfig.clinic_id == clinic_id)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        default_config = _default_ai_config()
        config = AIConfig(
            clinic_id=clinic_id,
            enabled=default_config["enabled"],
            provider=default_config["provider"],
            model=default_config["model"],
            max_tokens=default_config["max_tokens"],
            temperature=default_config["temperature"],
            features=default_config["features"],
            usage_stats=default_config["usage_stats"]
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
    
    return config


@router.get("")
async def get_ai_config(
    clinic_id: Optional[int] = Query(None, description="Clinic ID (required for non-SuperAdmin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get AI configuration for a clinic
    
    - SuperAdmin: can specify clinic_id or get all configs
    - Admin: gets config for their own clinic
    """
    # Determine clinic_id
    if current_user.role == "admin" and current_user.role_id == 1:  # SuperAdmin
        if not clinic_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="clinic_id is required for SuperAdmin"
            )
        target_clinic_id = clinic_id
    else:
        # Regular admin gets their own clinic
        target_clinic_id = current_user.clinic_id
    
    # Check license (SuperAdmin can view even without license or AI module enabled)
    is_superadmin = current_user.role == "admin" and current_user.role_id == 1
    license_obj = await _get_clinic_license(db, target_clinic_id, check_ai_module=False)
    
    # For non-SuperAdmin, require license
    if not license_obj and not is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clinic does not have a license"
        )
    
    # Get or create config
    config = await _get_or_create_ai_config(db, target_clinic_id)
    
    # Decrypt API key for response
    api_key = decrypt(config.api_key_encrypted) if config.api_key_encrypted else ""
    
    result = config.to_dict(include_api_key=True)
    result["api_key"] = api_key
    
    # Handle license and token limits
    if license_obj:
        # Get token limit from license
        token_limit = license_obj.ai_token_limit
        if token_limit is None:
            # Calculate from plan if not explicitly set
            token_limit = _get_token_limit_by_plan(license_obj.plan)
        
        # Check if AI module is enabled
        ai_enabled = "ai" in license_obj.modules or "api" in license_obj.modules
        result["ai_module_enabled"] = ai_enabled
        
        if ai_enabled:
            result["token_limit"] = token_limit
            result["token_limit_type"] = "unlimited" if token_limit == -1 else "limited"
            result["tokens_remaining"] = (
                -1 if token_limit == -1
                else max(0, token_limit - config.get_monthly_token_usage())
            )
        else:
            # Return defaults if AI module not enabled
            result["token_limit"] = None
            result["token_limit_type"] = "disabled"
            result["tokens_remaining"] = None
    else:
        # No license - SuperAdmin can still view but with warnings
        result["ai_module_enabled"] = False
        result["token_limit"] = None
        result["token_limit_type"] = "no_license"
        result["tokens_remaining"] = None
        result["warning"] = "Clinic does not have a license. Please create a license and enable the AI module first."
    
    return result


@router.put("")
async def update_ai_config(
    config_data: Dict[str, Any],
    clinic_id: Optional[int] = Query(None, description="Clinic ID (required for non-SuperAdmin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update AI configuration for a clinic
    """
    # Determine clinic_id
    if current_user.role == "admin" and current_user.role_id == 1:  # SuperAdmin
        if not clinic_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="clinic_id is required for SuperAdmin"
            )
        target_clinic_id = clinic_id
    else:
        target_clinic_id = current_user.clinic_id
    
    # Check license (SuperAdmin can update even without license or AI module enabled)
    is_superadmin = current_user.role == "admin" and current_user.role_id == 1
    license_obj = await _get_clinic_license(db, target_clinic_id, check_ai_module=False)
    
    # For non-SuperAdmin, require license
    if not license_obj and not is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clinic does not have a license"
        )
    
    # Check if AI module is enabled (only for non-SuperAdmin)
    if license_obj:
        ai_enabled = "ai" in license_obj.modules or "api" in license_obj.modules
        if not ai_enabled and not is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI module is not enabled for this clinic's license. Please enable the AI module in the license first."
            )
    
    # Get or create config
    config = await _get_or_create_ai_config(db, target_clinic_id)
    
    # Validate provider
    valid_providers = ["openai", "google", "anthropic", "azure"]
    if config_data.get("provider") and config_data["provider"] not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}"
        )
    
    # Update fields
    if "enabled" in config_data:
        config.enabled = config_data["enabled"]
    if "provider" in config_data:
        config.provider = config_data["provider"]
    if "model" in config_data:
        config.model = config_data["model"]
    if "base_url" in config_data:
        config.base_url = config_data["base_url"] or None
    if "max_tokens" in config_data:
        config.max_tokens = config_data["max_tokens"]
    if "temperature" in config_data:
        config.temperature = config_data["temperature"]
    if "features" in config_data:
        config.features = config_data["features"]
    
    # Encrypt API key if provided
    if "api_key" in config_data and config_data["api_key"]:
        encrypted_key = encrypt(config_data["api_key"])
        if encrypted_key:
            config.api_key_encrypted = encrypted_key
    
    config.updated_at = datetime.now(timezone.utc)
    
    try:
        await db.commit()
        await db.refresh(config)
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update AI configuration: {str(e)}"
        )
    
    # Return updated config
    api_key = decrypt(config.api_key_encrypted) if config.api_key_encrypted else ""
    result = config.to_dict(include_api_key=True)
    result["api_key"] = api_key
    
    # Handle license and token limits
    if license_obj:
        token_limit = license_obj.ai_token_limit
        if token_limit is None:
            token_limit = _get_token_limit_by_plan(license_obj.plan)
        
        ai_enabled = "ai" in license_obj.modules or "api" in license_obj.modules
        result["ai_module_enabled"] = ai_enabled
        
        if ai_enabled:
            result["token_limit"] = token_limit
            result["token_limit_type"] = "unlimited" if token_limit == -1 else "limited"
            result["tokens_remaining"] = (
                -1 if token_limit == -1
                else max(0, token_limit - config.get_monthly_token_usage())
            )
        else:
            result["token_limit"] = None
            result["token_limit_type"] = "disabled"
            result["tokens_remaining"] = None
    else:
        # No license - SuperAdmin can still save but with warnings
        result["ai_module_enabled"] = False
        result["token_limit"] = None
        result["token_limit_type"] = "no_license"
        result["tokens_remaining"] = None
        result["warning"] = "Clinic does not have a license. Please create a license and enable the AI module first."
    
    return {
        "message": "AI configuration updated successfully",
        "config": result
    }


@router.post("/test-connection")
async def test_ai_connection(
    config: Optional[Dict[str, Any]] = Body(None),
    clinic_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Test AI connection with provided or saved credentials
    """
    import time
    start_time = time.time()
    
    # Determine clinic_id
    if current_user.role == "admin" and current_user.role_id == 1:  # SuperAdmin
        if not clinic_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="clinic_id is required for SuperAdmin"
            )
        target_clinic_id = clinic_id
    else:
        target_clinic_id = current_user.clinic_id
    
    # Get provider and model from config or saved config
    provider = "openai"
    model = "gpt-4"
    api_key = None
    
    if config:
        provider = config.get("provider", provider)
        model = config.get("model", model)
        api_key = config.get("api_key")
    else:
        # Use saved config
        ai_config = await _get_or_create_ai_config(db, target_clinic_id)
        provider = ai_config.provider or provider
        model = ai_config.model or model
        api_key = decrypt(ai_config.api_key_encrypted) if ai_config.api_key_encrypted else None
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is required to test connection"
        )
    
    # Get additional config if using saved config
    base_url = None
    max_tokens = 2000
    temperature = 0.7
    
    if not config:
        ai_config = await _get_or_create_ai_config(db, target_clinic_id)
        base_url = ai_config.base_url
        max_tokens = ai_config.max_tokens
        temperature = ai_config.temperature
    else:
        base_url = config.get("base_url")
        max_tokens = config.get("max_tokens", 2000)
        temperature = config.get("temperature", 0.7)
    
    # Encrypt API key for service (it will decrypt it)
    api_key_encrypted = encrypt(api_key) if api_key else None
    
    # Test connection using AI service
    try:
        ai_service = create_ai_service(
            provider=provider,
            api_key_encrypted=api_key_encrypted or api_key,  # Pass encrypted or plain if encryption fails
            model=model,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        result = await ai_service.test_connection()
        return result
    
    except AIServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(e)}"
        )


@router.get("/stats")
async def get_ai_stats(
    clinic_id: Optional[int] = Query(None, description="Clinic ID (required for non-SuperAdmin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get AI usage statistics for a clinic
    """
    # Determine clinic_id
    if current_user.role == "admin" and current_user.role_id == 1:  # SuperAdmin
        if not clinic_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="clinic_id is required for SuperAdmin"
            )
        target_clinic_id = clinic_id
    else:
        target_clinic_id = current_user.clinic_id
    
    # Get config
    config = await _get_or_create_ai_config(db, target_clinic_id)
    
    # Get license for token limit (don't check AI module for stats - allow viewing even if not enabled)
    license_obj = await _get_clinic_license(db, target_clinic_id, check_ai_module=False)
    token_limit = 0
    if license_obj:
        token_limit = license_obj.ai_token_limit
        if token_limit is None:
            token_limit = _get_token_limit_by_plan(license_obj.plan)
    
    stats = config.usage_stats.copy()
    stats["token_limit"] = token_limit
    stats["tokens_remaining"] = (
        -1 if token_limit == -1
        else max(0, token_limit - config.get_monthly_token_usage())
    )
    stats["token_usage_percentage"] = (
        0 if token_limit <= 0
        else min(100, (config.get_monthly_token_usage() / token_limit) * 100)
    )
    
    return stats


@router.post("/reset-monthly-usage")
async def reset_monthly_usage(
    clinic_id: Optional[int] = Query(None),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Reset monthly token usage for a clinic (SuperAdmin only)
    """
    if not clinic_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="clinic_id is required"
        )
    
    config = await _get_or_create_ai_config(db, clinic_id)
    
    # Reset monthly usage
    config.usage_stats["tokens_this_month"] = 0
    config.usage_stats["last_reset_date"] = datetime.now(timezone.utc).isoformat()
    config.updated_at = datetime.now(timezone.utc)
    
    try:
        await db.commit()
        await db.refresh(config)
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset monthly usage: {str(e)}"
        )
    
    return {
        "message": "Monthly usage reset successfully",
        "reset_date": config.usage_stats["last_reset_date"]
    }

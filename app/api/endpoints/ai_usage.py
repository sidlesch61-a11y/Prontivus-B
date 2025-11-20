"""
AI Usage API Endpoints
Handles actual AI usage (analysis, suggestions, etc.) with token tracking
"""

from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import get_async_session
from app.core.auth import get_current_user
from app.models import User, AIConfig, License
from app.services.encryption_service import decrypt
from app.services.ai_service import create_ai_service, AIServiceError

router = APIRouter(prefix="/ai", tags=["AI Usage"])


async def _get_ai_config_with_validation(
    db: AsyncSession,
    clinic_id: int,
    check_enabled: bool = True
) -> Tuple[AIConfig, License]:
    """
    Get AI config and validate license/token limits
    
    Returns:
        Tuple of (AIConfig, License)
    """
    # Get AI config
    result = await db.execute(
        select(AIConfig)
        .where(AIConfig.clinic_id == clinic_id)
    )
    ai_config = result.scalar_one_or_none()
    
    if not ai_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI configuration not found for this clinic"
        )
    
    if check_enabled and not ai_config.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI is not enabled for this clinic"
        )
    
    if not ai_config.api_key_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is not configured"
        )
    
    # Get license
    result = await db.execute(
        select(License)
        .where(License.clinic_id == clinic_id)
        .where(License.is_active == True)
        .options(selectinload(License.clinic))
    )
    license_obj = result.scalar_one_or_none()
    
    if not license_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active license found for this clinic"
        )
    
    # Check if AI module is enabled
    if "ai" not in license_obj.modules and "api" not in license_obj.modules:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI module is not enabled for this clinic's license"
        )
    
    return ai_config, license_obj


async def _update_token_usage(
    db: AsyncSession,
    ai_config: AIConfig,
    tokens_used: int,
    response_time_ms: int,
    success: bool = True
):
    """
    Update token usage statistics
    
    Args:
        db: Database session
        ai_config: AI config object
        tokens_used: Number of tokens used
        response_time_ms: Response time in milliseconds
        success: Whether the request was successful
    """
    stats = ai_config.usage_stats.copy()
    
    # Update token counts
    stats["total_tokens"] = stats.get("total_tokens", 0) + tokens_used
    stats["tokens_this_month"] = stats.get("tokens_this_month", 0) + tokens_used
    
    # Update request counts
    stats["requests_count"] = stats.get("requests_count", 0) + 1
    if success:
        stats["successful_requests"] = stats.get("successful_requests", 0) + 1
    else:
        stats["failed_requests"] = stats.get("failed_requests", 0) + 1
    
    # Update response time (rolling average)
    current_avg = stats.get("average_response_time_ms", 0)
    request_count = stats.get("successful_requests", 1)
    stats["average_response_time_ms"] = (
        (current_avg * (request_count - 1) + response_time_ms) / request_count
        if request_count > 0
        else response_time_ms
    )
    
    # Update last request date
    stats["last_request_date"] = datetime.now(timezone.utc).isoformat()
    
    # Check if we need to reset monthly usage
    last_reset = stats.get("last_reset_date")
    now = datetime.now(timezone.utc)
    
    if not last_reset:
        stats["last_reset_date"] = now.isoformat()
    else:
        last_reset_date = datetime.fromisoformat(last_reset.replace('Z', '+00:00'))
        # Reset if it's a new month
        if now.year > last_reset_date.year or (
            now.year == last_reset_date.year and now.month > last_reset_date.month
        ):
            stats["tokens_this_month"] = tokens_used
            stats["last_reset_date"] = now.isoformat()
    
    ai_config.usage_stats = stats
    ai_config.updated_at = now
    
    await db.commit()
    await db.refresh(ai_config)


@router.post("/analyze-clinical")
async def analyze_clinical_data(
    clinical_data: Dict[str, Any] = Body(...),
    analysis_type: str = Body("general", description="Type of analysis: general, diagnosis, treatment, risk"),
    clinic_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Analyze clinical data using AI
    
    Args:
        clinical_data: Dictionary containing clinical information
        analysis_type: Type of analysis
        clinic_id: Optional clinic ID (for SuperAdmin)
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
    
    # Get and validate config
    ai_config, license_obj = await _get_ai_config_with_validation(db, target_clinic_id)
    
    # Check token limit
    token_limit = license_obj.ai_token_limit
    if token_limit is None:
        # Get default limit by plan
        plan_limits = {
            "basic": 10000,
            "standard": 50000,
            "premium": 200000,
            "enterprise": -1  # Unlimited
        }
        token_limit = plan_limits.get(license_obj.plan.lower(), 10000)
    
    # Estimate tokens needed (rough: 1 token ≈ 4 characters)
    estimated_tokens = len(str(clinical_data)) // 4 + ai_config.max_tokens
    
    if token_limit > 0 and not ai_config.can_use_tokens(estimated_tokens, token_limit):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Token limit exceeded. Monthly limit: {token_limit}, Used: {ai_config.get_monthly_token_usage()}, Required: {estimated_tokens}"
        )
    
    # Create AI service
    try:
        ai_service = create_ai_service(
            provider=ai_config.provider,
            api_key_encrypted=ai_config.api_key_encrypted,
            model=ai_config.model,
            base_url=ai_config.base_url,
            max_tokens=ai_config.max_tokens,
            temperature=ai_config.temperature
        )
        
        # Analyze clinical data
        analysis_text, usage = await ai_service.analyze_clinical_data(
            clinical_data=clinical_data,
            analysis_type=analysis_type
        )
        
        # Update token usage
        await _update_token_usage(
            db=db,
            ai_config=ai_config,
            tokens_used=usage["tokens_used"],
            response_time_ms=usage["response_time_ms"],
            success=True
        )
        
        # Update documents processed
        stats = ai_config.usage_stats.copy()
        stats["documents_processed"] = stats.get("documents_processed", 0) + 1
        ai_config.usage_stats = stats
        await db.commit()
        
        return {
            "analysis": analysis_text,
            "analysis_type": analysis_type,
            "tokens_used": usage["tokens_used"],
            "response_time_ms": usage["response_time_ms"]
        }
    
    except AIServiceError as e:
        await _update_token_usage(
            db=db,
            ai_config=ai_config,
            tokens_used=0,
            response_time_ms=0,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI analysis failed: {str(e)}"
        )


@router.post("/suggest-diagnosis")
async def suggest_diagnosis(
    symptoms: List[str] = Body(...),
    patient_history: Optional[Dict[str, Any]] = Body(None),
    clinic_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Suggest possible diagnoses based on symptoms
    
    Args:
        symptoms: List of symptoms
        patient_history: Optional patient history
        clinic_id: Optional clinic ID (for SuperAdmin)
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
    
    # Get and validate config
    ai_config, license_obj = await _get_ai_config_with_validation(db, target_clinic_id)
    
    # Check token limit
    token_limit = license_obj.ai_token_limit
    if token_limit is None:
        plan_limits = {
            "basic": 10000,
            "standard": 50000,
            "premium": 200000,
            "enterprise": -1
        }
        token_limit = plan_limits.get(license_obj.plan.lower(), 10000)
    
    # Estimate tokens needed
    estimated_tokens = (len(" ".join(symptoms)) + len(str(patient_history or ""))) // 4 + ai_config.max_tokens
    
    if token_limit > 0 and not ai_config.can_use_tokens(estimated_tokens, token_limit):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Token limit exceeded. Monthly limit: {token_limit}, Used: {ai_config.get_monthly_token_usage()}, Required: {estimated_tokens}"
        )
    
    # Create AI service
    try:
        ai_service = create_ai_service(
            provider=ai_config.provider,
            api_key_encrypted=ai_config.api_key_encrypted,
            model=ai_config.model,
            base_url=ai_config.base_url,
            max_tokens=ai_config.max_tokens,
            temperature=ai_config.temperature
        )
        
        # Get diagnosis suggestions
        suggestions, usage = await ai_service.suggest_diagnosis(
            symptoms=symptoms,
            patient_history=patient_history
        )
        
        # Update token usage
        await _update_token_usage(
            db=db,
            ai_config=ai_config,
            tokens_used=usage["tokens_used"],
            response_time_ms=usage["response_time_ms"],
            success=True
        )
        
        # Update suggestions generated
        stats = ai_config.usage_stats.copy()
        stats["suggestions_generated"] = stats.get("suggestions_generated", 0) + len(suggestions)
        ai_config.usage_stats = stats
        await db.commit()
        
        return {
            "suggestions": suggestions,
            "tokens_used": usage["tokens_used"],
            "response_time_ms": usage["response_time_ms"]
        }
    
    except AIServiceError as e:
        await _update_token_usage(
            db=db,
            ai_config=ai_config,
            tokens_used=0,
            response_time_ms=0,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI diagnosis suggestion failed: {str(e)}"
        )


@router.post("/suggest-treatment")
async def suggest_treatment(
    diagnosis: str = Body(...),
    patient_data: Optional[Dict[str, Any]] = Body(None),
    clinic_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate treatment suggestions for a diagnosis
    
    Args:
        diagnosis: Diagnosis name
        patient_data: Optional patient data (allergies, medications, etc.)
        clinic_id: Optional clinic ID (for SuperAdmin)
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
    
    # Get and validate config
    ai_config, license_obj = await _get_ai_config_with_validation(db, target_clinic_id)
    
    # Check token limit
    token_limit = license_obj.ai_token_limit
    if token_limit is None:
        plan_limits = {
            "basic": 10000,
            "standard": 50000,
            "premium": 200000,
            "enterprise": -1
        }
        token_limit = plan_limits.get(license_obj.plan.lower(), 10000)
    
    # Estimate tokens needed
    estimated_tokens = (len(diagnosis) + len(str(patient_data or ""))) // 4 + ai_config.max_tokens
    
    if token_limit > 0 and not ai_config.can_use_tokens(estimated_tokens, token_limit):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Token limit exceeded. Monthly limit: {token_limit}, Used: {ai_config.get_monthly_token_usage()}, Required: {estimated_tokens}"
        )
    
    # Create AI service
    try:
        ai_service = create_ai_service(
            provider=ai_config.provider,
            api_key_encrypted=ai_config.api_key_encrypted,
            model=ai_config.model,
            base_url=ai_config.base_url,
            max_tokens=ai_config.max_tokens,
            temperature=ai_config.temperature
        )
        
        # Get treatment suggestions
        suggestions, usage = await ai_service.generate_treatment_suggestions(
            diagnosis=diagnosis,
            patient_data=patient_data
        )
        
        # Update token usage
        await _update_token_usage(
            db=db,
            ai_config=ai_config,
            tokens_used=usage["tokens_used"],
            response_time_ms=usage["response_time_ms"],
            success=True
        )
        
        # Update suggestions generated
        stats = ai_config.usage_stats.copy()
        stats["suggestions_generated"] = stats.get("suggestions_generated", 0) + len(suggestions)
        ai_config.usage_stats = stats
        await db.commit()
        
        return {
            "suggestions": suggestions,
            "tokens_used": usage["tokens_used"],
            "response_time_ms": usage["response_time_ms"]
        }
    
    except AIServiceError as e:
        await _update_token_usage(
            db=db,
            ai_config=ai_config,
            tokens_used=0,
            response_time_ms=0,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI treatment suggestion failed: {str(e)}"
        )


@router.post("/chat")
async def ai_chat(
    message: str = Body(...),
    context: Optional[List[Dict[str, str]]] = Body(None),
    system_prompt: Optional[str] = Body(None),
    clinic_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    General AI chat/completion endpoint
    
    Args:
        message: User message
        context: Optional conversation context
        system_prompt: Optional system prompt
        clinic_id: Optional clinic ID (for SuperAdmin)
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
    
    # Get and validate config
    ai_config, license_obj = await _get_ai_config_with_validation(db, target_clinic_id)
    
    # Check token limit
    token_limit = license_obj.ai_token_limit
    if token_limit is None:
        plan_limits = {
            "basic": 10000,
            "standard": 50000,
            "premium": 200000,
            "enterprise": -1
        }
        token_limit = plan_limits.get(license_obj.plan.lower(), 10000)
    
    # Estimate tokens needed
    estimated_tokens = (len(message) + len(system_prompt or "") + len(str(context or ""))) // 4 + ai_config.max_tokens
    
    if token_limit > 0 and not ai_config.can_use_tokens(estimated_tokens, token_limit):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Token limit exceeded. Monthly limit: {token_limit}, Used: {ai_config.get_monthly_token_usage()}, Required: {estimated_tokens}"
        )
    
    # Create AI service
    try:
        ai_service = create_ai_service(
            provider=ai_config.provider,
            api_key_encrypted=ai_config.api_key_encrypted,
            model=ai_config.model,
            base_url=ai_config.base_url,
            max_tokens=ai_config.max_tokens,
            temperature=ai_config.temperature
        )
        
        # Generate response
        response_text, usage = await ai_service.generate_completion(
            prompt=message,
            system_prompt=system_prompt,
            context=context
        )
        
        # Update token usage
        await _update_token_usage(
            db=db,
            ai_config=ai_config,
            tokens_used=usage["tokens_used"],
            response_time_ms=usage["response_time_ms"],
            success=True
        )
        
        return {
            "response": response_text,
            "tokens_used": usage["tokens_used"],
            "response_time_ms": usage["response_time_ms"]
        }
    
    except AIServiceError as e:
        await _update_token_usage(
            db=db,
            ai_config=ai_config,
            tokens_used=0,
            response_time_ms=0,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI chat failed: {str(e)}"
        )


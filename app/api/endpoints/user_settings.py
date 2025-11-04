"""
User Settings API endpoints
Handles user preferences and settings management
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.auth import get_current_user
from app.models import User, UserSettings
from app.schemas.user_settings import (
    UserSettingsUpdate,
    UserSettingsResponse,
    UserSettingsFullResponse,
    NotificationSettings,
    PrivacySettings,
    AppearanceSettings,
    SecuritySettings
)
from database import get_async_session

router = APIRouter(prefix="/settings", tags=["User Settings"])


def get_default_settings():
    """Get default settings structure"""
    return {
        "notifications": NotificationSettings().model_dump(),
        "privacy": PrivacySettings().model_dump(),
        "appearance": AppearanceSettings().model_dump(),
        "security": SecuritySettings().model_dump(),
    }


@router.get("/me", response_model=UserSettingsFullResponse)
async def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get current user's settings
    Returns settings with profile information
    """
    # Get or create user settings
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    user_settings = result.scalar_one_or_none()
    
    # If no settings exist, return defaults
    if not user_settings:
        defaults = get_default_settings()
        return UserSettingsFullResponse(
            profile={
                "firstName": current_user.first_name or "",
                "lastName": current_user.last_name or "",
                "email": current_user.email,
                "phone": "",
            },
            notifications=defaults["notifications"],
            privacy=defaults["privacy"],
            appearance=defaults["appearance"],
            security=defaults["security"],
        )
    
    # Return settings with profile info
    return UserSettingsFullResponse(
        profile={
            "firstName": current_user.first_name or "",
            "lastName": current_user.last_name or "",
            "email": current_user.email,
            "phone": user_settings.phone or "",
        },
        notifications=user_settings.notifications or get_default_settings()["notifications"],
        privacy=user_settings.privacy or get_default_settings()["privacy"],
        appearance=user_settings.appearance or get_default_settings()["appearance"],
        security=user_settings.security or get_default_settings()["security"],
    )


@router.put("/me", response_model=UserSettingsResponse)
async def update_user_settings(
    settings_update: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update current user's settings
    Creates settings if they don't exist
    """
    # Get or create user settings
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    user_settings = result.scalar_one_or_none()
    
    if not user_settings:
        # Create new settings with defaults
        defaults = get_default_settings()
        user_settings = UserSettings(
            user_id=current_user.id,
            phone=settings_update.phone,
            notifications=settings_update.notifications or defaults["notifications"],
            privacy=settings_update.privacy or defaults["privacy"],
            appearance=settings_update.appearance or defaults["appearance"],
            security=settings_update.security or defaults["security"],
        )
        db.add(user_settings)
    else:
        # Update existing settings
        if settings_update.phone is not None:
            user_settings.phone = settings_update.phone
        if settings_update.notifications is not None:
            user_settings.notifications = settings_update.notifications
        if settings_update.privacy is not None:
            user_settings.privacy = settings_update.privacy
        if settings_update.appearance is not None:
            user_settings.appearance = settings_update.appearance
        if settings_update.security is not None:
            user_settings.security = settings_update.security
    
    try:
        await db.commit()
        await db.refresh(user_settings)
        return UserSettingsResponse.model_validate(user_settings)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}"
        )


@router.post("/me/profile")
async def update_user_profile(
    profile_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update user profile information (first_name, last_name, email)
    Also updates settings phone if provided
    """
    # Update user model fields
    if "firstName" in profile_data:
        current_user.first_name = profile_data["firstName"]
    if "lastName" in profile_data:
        current_user.last_name = profile_data["lastName"]
    if "email" in profile_data:
        # Check if email is already taken by another user
        result = await db.execute(
            select(User).where(
                User.email == profile_data["email"],
                User.id != current_user.id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use"
            )
        current_user.email = profile_data["email"]
    
    # Update or create settings for phone
    if "phone" in profile_data:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == current_user.id)
        )
        user_settings = result.scalar_one_or_none()
        
        if not user_settings:
            defaults = get_default_settings()
            user_settings = UserSettings(
                user_id=current_user.id,
                phone=profile_data["phone"],
                notifications=defaults["notifications"],
                privacy=defaults["privacy"],
                appearance=defaults["appearance"],
                security=defaults["security"],
            )
            db.add(user_settings)
        else:
            user_settings.phone = profile_data["phone"]
    
    try:
        await db.commit()
        return {"message": "Profile updated successfully"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


"""
User Settings API endpoints
Handles user preferences and settings management
"""
from typing import Optional
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from PIL import Image
import io

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
from app.services.email_service import email_service, check_email_notifications_enabled, send_notification_email_if_enabled
from app.services.push_service import push_service, check_push_notifications_enabled
from app.services.sms_service import sms_service, check_sms_notifications_enabled
from app.models.push_subscription import PushSubscription
from database import get_async_session

router = APIRouter(prefix="/settings", tags=["User Settings"])

# Avatar storage configuration
AVATAR_DIR = os.getenv("AVATAR_STORAGE_DIR", os.path.join("storage", "avatars"))
AVATAR_MAX_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]

# Ensure avatar directory exists
os.makedirs(AVATAR_DIR, exist_ok=True)


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
                "avatar": None,
            },
            notifications=defaults["notifications"],
            privacy=defaults["privacy"],
            appearance=defaults["appearance"],
            security=defaults["security"],
        )
    
    # Return settings with profile info
    # Use get() to handle None values, but preserve empty dicts
    defaults = get_default_settings()
    return UserSettingsFullResponse(
        profile={
            "firstName": current_user.first_name or "",
            "lastName": current_user.last_name or "",
            "email": current_user.email,
            "phone": user_settings.phone or "",
            "avatar": user_settings.avatar_url or None,
        },
        notifications=user_settings.notifications if user_settings.notifications is not None else defaults["notifications"],
        privacy=user_settings.privacy if user_settings.privacy is not None else defaults["privacy"],
        appearance=user_settings.appearance if user_settings.appearance is not None else defaults["appearance"],
        security=user_settings.security if user_settings.security is not None else defaults["security"],
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
        # Create new settings - use provided values or defaults
        defaults = get_default_settings()
        user_settings = UserSettings(
            user_id=current_user.id,
            phone=settings_update.phone if settings_update.phone is not None else None,
            notifications=settings_update.notifications if settings_update.notifications is not None else defaults["notifications"],
            privacy=settings_update.privacy if settings_update.privacy is not None else defaults["privacy"],
            appearance=settings_update.appearance if settings_update.appearance is not None else defaults["appearance"],
            security=settings_update.security if settings_update.security is not None else defaults["security"],
        )
        db.add(user_settings)
    else:
        # Update existing settings - frontend sends complete objects, so replace directly
        if settings_update.phone is not None:
            user_settings.phone = settings_update.phone
        if settings_update.notifications is not None:
            # Replace with the new notifications dict
            user_settings.notifications = settings_update.notifications
        if settings_update.privacy is not None:
            # Replace with the new privacy dict
            user_settings.privacy = settings_update.privacy
        if settings_update.appearance is not None:
            # Replace with the new appearance dict
            user_settings.appearance = settings_update.appearance
        if settings_update.security is not None:
            # Replace with the new security dict
            user_settings.security = settings_update.security
    
    try:
        # Ensure all JSON fields are properly set (not None)
        if user_settings.notifications is None:
            user_settings.notifications = get_default_settings()["notifications"]
        if user_settings.privacy is None:
            user_settings.privacy = get_default_settings()["privacy"]
        if user_settings.appearance is None:
            user_settings.appearance = get_default_settings()["appearance"]
        if user_settings.security is None:
            user_settings.security = get_default_settings()["security"]
        
        await db.commit()
        await db.refresh(user_settings)
        
        # Verify the data was saved
        if user_settings.notifications is None or user_settings.privacy is None:
            raise ValueError("Settings were not properly saved to database")
        
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


@router.post("/me/avatar")
async def upload_avatar(
    avatar: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Upload user avatar image
    Accepts image files (JPEG, PNG, GIF, WebP) up to 5MB
    """
    # Validate file exists
    if not avatar.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    # Validate file type by content-type or extension
    filename_lower = avatar.filename.lower()
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    has_valid_extension = any(filename_lower.endswith(ext) for ext in valid_extensions)
    
    if avatar.content_type and avatar.content_type not in ALLOWED_IMAGE_TYPES:
        if not has_valid_extension:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES)}"
            )
    elif not avatar.content_type and not has_valid_extension:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Please upload an image file (JPG, PNG, GIF, or WebP)"
        )
    
    # Read file content
    content = await avatar.read()
    
    # Validate file size
    if len(content) > AVATAR_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {AVATAR_MAX_SIZE / (1024 * 1024)}MB"
        )
    
    # Validate and process image
    try:
        image = Image.open(io.BytesIO(content))
        # Convert to RGB if necessary (for PNG with transparency)
        if image.mode in ('RGBA', 'LA', 'P'):
            rgb_image = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            rgb_image.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = rgb_image
        
        # Resize image if too large (max 512x512)
        max_size = 512
        if image.width > max_size or image.height > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Generate unique filename
        file_ext = Path(avatar.filename or 'avatar.jpg').suffix or '.jpg'
        if file_ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            file_ext = '.jpg'
        
        filename = f"{current_user.id}_{uuid.uuid4().hex[:8]}{file_ext}"
        
        # Create user-specific directory
        user_dir = os.path.join(AVATAR_DIR, str(current_user.clinic_id))
        os.makedirs(user_dir, exist_ok=True)
        
        file_path = os.path.join(user_dir, filename)
        
        # Save image
        image.save(file_path, 'JPEG', quality=85, optimize=True)
        
        # Generate URL path (relative to storage)
        avatar_url = f"/storage/avatars/{current_user.clinic_id}/{filename}"
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image file: {str(e)}"
        )
    
    # Get or create user settings
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    user_settings = result.scalar_one_or_none()
    
    if not user_settings:
        defaults = get_default_settings()
        user_settings = UserSettings(
            user_id=current_user.id,
            avatar_url=avatar_url,
            notifications=defaults["notifications"],
            privacy=defaults["privacy"],
            appearance=defaults["appearance"],
            security=defaults["security"],
        )
        db.add(user_settings)
    else:
        # Delete old avatar if exists
        if user_settings.avatar_url:
            old_path = user_settings.avatar_url.replace("/storage/avatars/", AVATAR_DIR + "/")
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except:
                    pass  # Ignore errors when deleting old file
        
        user_settings.avatar_url = avatar_url
    
    try:
        await db.commit()
        await db.refresh(user_settings)
        
        # Return full URL (use relative path, frontend will handle base URL)
        # In production, you might want to use a CDN or storage service URL
        base_url = os.getenv("API_BASE_URL", "")
        if base_url:
            full_url = f"{base_url}{avatar_url}"
        else:
            # Return relative path, frontend will construct full URL
            full_url = avatar_url
        
        return {
            "avatar_url": full_url,
            "avatar": full_url,
            "message": "Avatar uploaded successfully"
        }
    except Exception as e:
        await db.rollback()
        # Clean up uploaded file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save avatar: {str(e)}"
        )


@router.post("/me/change-password")
async def change_password(
    password_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Change user password
    All password fields are required if any field is provided
    """
    from app.core.auth import verify_password, hash_password
    
    current_password = password_data.get("currentPassword")
    new_password = password_data.get("newPassword")
    confirm_password = password_data.get("confirmPassword")
    
    # Check if user is trying to change password (at least one field is provided)
    is_changing_password = bool(current_password or new_password or confirm_password)
    
    if not is_changing_password:
        # No password change attempted, return success
        return {"message": "No password change requested"}
    
    # If any field is provided, all fields are required
    if not current_password or not new_password or not confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Todos os campos de senha são obrigatórios se você desejar alterar a senha"
        )
    
    if new_password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match"
        )
    
    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long"
        )
    
    # Verify current password
    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    # Update password
    current_user.hashed_password = hash_password(new_password)
    
    try:
        await db.commit()
        await db.refresh(current_user)
        return {"message": "Password changed successfully"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to change password: {str(e)}"
        )


@router.delete("/me/avatar")
async def delete_avatar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete user avatar
    """
    # Get user settings
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    user_settings = result.scalar_one_or_none()
    
    if not user_settings or not user_settings.avatar_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Avatar not found"
        )
    
    # Delete file
    file_path = user_settings.avatar_url.replace("/storage/avatars/", AVATAR_DIR + "/")
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            pass  # Continue even if file deletion fails
    
    # Remove avatar URL from settings
    user_settings.avatar_url = None
    
    try:
        await db.commit()
        return {"message": "Avatar deleted successfully"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete avatar: {str(e)}"
        )


@router.post("/me/test-email")
async def test_email_notification(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Send a test email notification to verify email settings are working
    """
    if not current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User email not found"
        )
    
    # Check if email notifications are enabled
    email_enabled = await check_email_notifications_enabled(current_user.id, db)
    
    if not email_enabled:
        return {
            "message": "Email notifications are disabled in your settings",
            "email_sent": False,
            "email_enabled": False
        }
    
    # Send test email
    success = await email_service.send_notification_email(
        to_email=current_user.email,
        notification_title="Teste de Notificação por E-mail",
        notification_message=(
            "Este é um email de teste do sistema Prontivus. "
            "Se você recebeu este email, significa que suas configurações de notificação por e-mail estão funcionando corretamente."
        ),
        notification_type="info",
        action_url=None,
    )
    
    if success:
        return {
            "message": "Email de teste enviado com sucesso",
            "email_sent": True,
            "email_enabled": True,
            "email_address": current_user.email
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao enviar email de teste. Verifique as configurações SMTP."
        )


@router.post("/me/push-subscription")
async def subscribe_push_notification(
    subscription_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Subscribe to push notifications
    """
    try:
        endpoint = subscription_data.get("endpoint")
        keys = subscription_data.get("keys", {})
        p256dh = keys.get("p256dh")
        auth = keys.get("auth")
        user_agent = subscription_data.get("userAgent")
        device_info = subscription_data.get("deviceInfo")
        
        if not endpoint or not p256dh or not auth:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid subscription data. Missing endpoint, p256dh, or auth."
            )
        
        # Check if subscription already exists
        result = await db.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == current_user.id,
                PushSubscription.endpoint == endpoint
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Update existing subscription
            existing.p256dh = p256dh
            existing.auth = auth
            existing.user_agent = user_agent
            existing.device_info = device_info
            existing.is_active = True
        else:
            # Create new subscription
            subscription = PushSubscription(
                user_id=current_user.id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                user_agent=user_agent,
                device_info=device_info,
                is_active=True,
            )
            db.add(subscription)
        
        await db.commit()
        return {"message": "Push subscription saved successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save push subscription: {str(e)}"
        )


@router.post("/me/push-subscription/unsubscribe")
async def unsubscribe_push_notification(
    subscription_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Unsubscribe from push notifications
    """
    try:
        endpoint = subscription_data.get("endpoint")
        
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Endpoint is required"
            )
        
        # Find and deactivate all subscriptions for user (or specific endpoint)
        if endpoint:
            result = await db.execute(
                select(PushSubscription).where(
                    PushSubscription.user_id == current_user.id,
                    PushSubscription.endpoint == endpoint
                )
            )
        else:
            result = await db.execute(
                select(PushSubscription).where(
                    PushSubscription.user_id == current_user.id
                )
            )
        
        subscriptions = result.scalars().all()
        
        if subscriptions:
            for subscription in subscriptions:
                subscription.is_active = False
            await db.commit()
            return {"message": f"Push subscription(s) removed successfully ({len(subscriptions)} subscription(s))"}
        else:
            return {"message": "No active subscriptions found"}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove push subscription: {str(e)}"
        )


@router.get("/me/push-public-key")
async def get_push_public_key():
    """
    Get VAPID public key for push notification subscription
    Returns 200 with enabled: false if VAPID keys are not configured
    """
    public_key = push_service.get_vapid_public_key()
    if not public_key:
        # Return 200 with enabled: false instead of 503
        # This allows frontend to handle gracefully
        return {
            "publicKey": "",
            "enabled": False,
            "message": "Push notifications are not configured. VAPID keys not set."
        }
    return {
        "publicKey": public_key,
        "enabled": True
    }


@router.post("/me/test-push")
async def test_push_notification(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Send a test push notification to verify push settings are working
    """
    # Check if push notifications are enabled
    push_enabled = await check_push_notifications_enabled(current_user.id, db)
    
    if not push_enabled:
        return {
            "message": "Push notifications are disabled in your settings",
            "push_sent": False,
            "push_enabled": False
        }
    
    # Send test push notification
    count = await push_service.send_notification_to_user(
        user_id=current_user.id,
        title="Teste de Notificação Push",
        body="Este é um teste do sistema Prontivus. Se você recebeu esta notificação, suas configurações de push estão funcionando corretamente.",
        icon="/favicon.png",
        tag="test-notification",
        db=db,
    )
    
    if count > 0:
        return {
            "message": f"Notificação push de teste enviada com sucesso para {count} dispositivo(s)",
            "push_sent": True,
            "push_enabled": True,
            "devices_notified": count
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhuma assinatura push ativa encontrada. Por favor, permita notificações no seu navegador."
        )


@router.post("/me/test-sms")
async def test_sms_notification(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Send a test SMS notification to verify SMS settings are working
    """
    # Get user phone from settings
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    user_settings = result.scalar_one_or_none()
    
    user_phone = None
    if user_settings and user_settings.phone:
        user_phone = user_settings.phone
    
    if not user_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Número de telefone não encontrado. Por favor, adicione um número de telefone nas configurações do perfil."
        )
    
    # Check if SMS notifications are enabled
    sms_enabled = await check_sms_notifications_enabled(current_user.id, db)
    
    if not sms_enabled:
        return {
            "message": "Notificações SMS estão desabilitadas nas suas configurações",
            "sms_sent": False,
            "sms_enabled": False
        }
    
    # Send test SMS
    success = await sms_service.send_notification_sms(
        to_phone=user_phone,
        notification_title="Teste de Notificação SMS",
        notification_message=(
            "Este é um SMS de teste do sistema Prontivus. "
            "Se você recebeu esta mensagem, suas configurações de notificação SMS estão funcionando corretamente."
        ),
    )
    
    if success:
        return {
            "message": "SMS de teste enviado com sucesso",
            "sms_sent": True,
            "sms_enabled": True,
            "phone_number": user_phone
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao enviar SMS de teste. Verifique as configurações SMS (Twilio) e o número de telefone."
        )


@router.post("/me/test-appointment-reminder")
async def test_appointment_reminder(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Send a test appointment reminder notification
    """
    from app.services.notification_dispatcher import send_appointment_reminder
    from datetime import datetime, timedelta
    
    # Check if appointment reminders are enabled
    from app.services.notification_dispatcher import check_notification_type_enabled
    reminders_enabled = await check_notification_type_enabled(
        current_user.id,
        "appointmentReminders",
        db
    )
    
    if not reminders_enabled:
        return {
            "message": "Lembretes de consultas estão desabilitados nas suas configurações",
            "sent": False,
            "enabled": False
        }
    
    # Send test appointment reminder (scheduled for tomorrow)
    test_datetime = datetime.now() + timedelta(days=1)
    results = await send_appointment_reminder(
        user_id=current_user.id,
        appointment_title="Consulta de Teste",
        appointment_message="Este é um lembrete de teste do sistema Prontivus.",
        appointment_datetime=test_datetime,
        action_url="/secretaria/agendamentos",
        db=db,
    )
    
    channels_sent = []
    if results.get('email', {}).get('sent'):
        channels_sent.append('email')
    if results.get('sms', {}).get('sent'):
        channels_sent.append('SMS')
    if results.get('push', {}).get('sent'):
        channels_sent.append('push')
    
    if channels_sent:
        return {
            "message": f"Lembrete de consulta de teste enviado via: {', '.join(channels_sent)}",
            "sent": True,
            "enabled": True,
            "channels": channels_sent,
            "results": results
        }
    else:
        return {
            "message": "Nenhum canal de notificação ativo. Verifique suas configurações de email, SMS e push.",
            "sent": False,
            "enabled": True,
            "results": results
        }


@router.post("/me/test-system-update")
async def test_system_update(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Send a test system update notification
    """
    from app.services.notification_dispatcher import send_system_update
    from app.services.notification_dispatcher import check_notification_type_enabled
    
    # Check if system updates are enabled
    updates_enabled = await check_notification_type_enabled(
        current_user.id,
        "systemUpdates",
        db
    )
    
    if not updates_enabled:
        return {
            "message": "Atualizações do sistema estão desabilitadas nas suas configurações",
            "sent": False,
            "enabled": False
        }
    
    # Send test system update
    results = await send_system_update(
        user_id=current_user.id,
        update_title="Atualização do Sistema - Teste",
        update_message="Este é um teste de notificação de atualização do sistema Prontivus.",
        action_url="/settings",
        db=db,
    )
    
    channels_sent = []
    if results.get('email', {}).get('sent'):
        channels_sent.append('email')
    if results.get('sms', {}).get('sent'):
        channels_sent.append('SMS')
    if results.get('push', {}).get('sent'):
        channels_sent.append('push')
    
    if channels_sent:
        return {
            "message": f"Atualização do sistema de teste enviada via: {', '.join(channels_sent)}",
            "sent": True,
            "enabled": True,
            "channels": channels_sent,
            "results": results
        }
    else:
        return {
            "message": "Nenhum canal de notificação ativo. Verifique suas configurações de email, SMS e push.",
            "sent": False,
            "enabled": True,
            "results": results
        }


@router.post("/me/test-marketing")
async def test_marketing_notification(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Send a test marketing notification
    """
    from app.services.notification_dispatcher import send_marketing_notification
    from app.services.notification_dispatcher import check_notification_type_enabled
    
    # Check if marketing notifications are enabled
    marketing_enabled = await check_notification_type_enabled(
        current_user.id,
        "marketing",
        db
    )
    
    if not marketing_enabled:
        return {
            "message": "Notificações de marketing estão desabilitadas nas suas configurações",
            "sent": False,
            "enabled": False
        }
    
    # Send test marketing notification
    results = await send_marketing_notification(
        user_id=current_user.id,
        marketing_title="Oferta Especial - Teste",
        marketing_message="Este é um teste de notificação de marketing do sistema Prontivus.",
        action_url="/portal",
        db=db,
    )
    
    channels_sent = []
    if results.get('email', {}).get('sent'):
        channels_sent.append('email')
    if results.get('sms', {}).get('sent'):
        channels_sent.append('SMS')
    if results.get('push', {}).get('sent'):
        channels_sent.append('push')
    
    if channels_sent:
        return {
            "message": f"Notificação de marketing de teste enviada via: {', '.join(channels_sent)}",
            "sent": True,
            "enabled": True,
            "channels": channels_sent,
            "results": results
        }
    else:
        return {
            "message": "Nenhum canal de notificação ativo. Verifique suas configurações de email, SMS e push.",
            "sent": False,
            "enabled": True,
            "results": results
        }


@router.post("/me/test-privacy")
async def test_privacy_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Test privacy settings functionality
    Returns current privacy settings and their effects
    """
    from app.services.privacy_service import get_user_privacy_settings
    
    # Get current privacy settings
    privacy_settings = await get_user_privacy_settings(current_user.id, db)
    
    # Test each setting
    test_results = {
        "showOnlineStatus": {
            "enabled": privacy_settings.get("showOnlineStatus", True),
            "effect": "Seu status online será visível para outros" if privacy_settings.get("showOnlineStatus", True) else "Seu status online será oculto",
        },
        "allowDirectMessages": {
            "enabled": privacy_settings.get("allowDirectMessages", True),
            "effect": "Outros podem enviar mensagens diretas para você" if privacy_settings.get("allowDirectMessages", True) else "Outros não podem enviar mensagens diretas para você",
        },
        "dataSharing": {
            "enabled": privacy_settings.get("dataSharing", False),
            "effect": "Seus dados anonimizados podem ser usados para pesquisa" if privacy_settings.get("dataSharing", False) else "Seus dados não serão compartilhados para pesquisa",
        },
        "profileVisibility": {
            "value": privacy_settings.get("profileVisibility", "contacts"),
            "effect": {
                "public": "Seu perfil é visível para todos",
                "contacts": "Seu perfil é visível apenas para contatos",
                "private": "Seu perfil é privado",
            }.get(privacy_settings.get("profileVisibility", "contacts"), "Desconhecido"),
        },
    }
    
    return {
        "message": "Teste de configurações de privacidade concluído",
        "settings": privacy_settings,
        "test_results": test_results,
    }


@router.post("/me/2fa/setup")
async def setup_2fa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Setup Two Factor Authentication
    Returns QR code and secret for authenticator app
    """
    from app.services.two_factor_service import two_factor_service
    
    try:
        result = await two_factor_service.setup_2fa(
            user_id=current_user.id,
            user_email=current_user.email,
            db=db
        )
        return {
            "message": "2FA setup initiated. Scan the QR code with your authenticator app.",
            "secret": result["secret"],
            "qr_uri": result["qr_uri"],
            "qr_image": result["qr_image"],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup 2FA: {str(e)}"
        )


@router.post("/me/2fa/verify")
async def verify_2fa(
    request_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Verify 2FA code and enable 2FA
    """
    from app.services.two_factor_service import two_factor_service
    
    code = request_data.get("code", "")
    if not code or len(code) != 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code. Please enter a 6-digit code."
        )
    
    success = await two_factor_service.verify_and_enable_2fa(
        user_id=current_user.id,
        code=code,
        db=db
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code. Please try again."
        )
    
    return {
        "message": "2FA enabled successfully",
        "enabled": True
    }


@router.post("/me/2fa/disable")
async def disable_2fa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Disable Two Factor Authentication
    """
    from app.services.two_factor_service import two_factor_service
    
    success = await two_factor_service.disable_2fa(
        user_id=current_user.id,
        db=db
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disable 2FA"
        )
    
    return {
        "message": "2FA disabled successfully",
        "enabled": False
    }


@router.get("/me/2fa/status")
async def get_2fa_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get 2FA status
    """
    from app.services.two_factor_service import two_factor_service
    
    is_enabled = await two_factor_service.is_2fa_enabled(
        user_id=current_user.id,
        db=db
    )
    
    return {
        "enabled": is_enabled
    }


@router.post("/me/test-login-alert")
async def test_login_alert(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Send a test login alert
    """
    from app.services.login_alert_service import send_login_alert, should_send_login_alert
    
    # Check if login alerts are enabled
    alerts_enabled = await should_send_login_alert(current_user.id, db)
    
    if not alerts_enabled:
        return {
            "message": "Alertas de login estão desabilitados nas suas configurações",
            "sent": False,
            "enabled": False
        }
    
    # Send test login alert
    success = await send_login_alert(
        user_id=current_user.id,
        login_ip="127.0.0.1",
        user_agent="Test Login Alert",
        db=db
    )
    
    if success:
        return {
            "message": "Alerta de login de teste enviado com sucesso",
            "sent": True,
            "enabled": True
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao enviar alerta de login de teste"
        )


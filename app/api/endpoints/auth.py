"""
Authentication Endpoints
Handles user authentication, registration, and token management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import httpx
from typing import Optional

from database import get_db
from app.core.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password
)
from app.models import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    TokenResponse,
    RegisterRequest,
    MessageResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest
)
from config import settings
from app.services.login_alert_service import send_login_alert
from app.services.menu_service import MenuService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    User Login Endpoint
    
    Authenticates a user with username/email and password, returns JWT token.
    
    Args:
        login_data: Login credentials (username/email and password)
        db: Database session
        
    Returns:
        LoginResponse with access token, refresh token, and user data
        
    Raises:
        HTTPException: If credentials are invalid
    """
    # Authenticate user
    user = await authenticate_user(
        db,
        login_data.username_or_email,
        login_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify role if expected_role is provided
    if login_data.expected_role:
        expected_role = login_data.expected_role.lower()
        user_role = user.role.value.lower()
        
        if expected_role == "staff":
            # Staff roles: admin, secretary, doctor
            if user_role not in ["admin", "secretary", "doctor"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. This login is restricted to staff members only."
                )
        elif expected_role == "patient":
            # Patient role only
            if user_role != "patient":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. This login is restricted to patients only."
                )
    
    # Get user permissions and role from menu service
    menu_service = MenuService(db)
    user_role = await menu_service.get_user_role(user.id)
    user_permissions = await menu_service.get_user_permissions(user.id)
    menu_structure = await menu_service.get_menu_structure(user.id)
    
    # Create token data with permissions
    token_data = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role.value,
        "role_id": user.role_id,
        "role_name": user_role.name if user_role else None,
        "clinic_id": user.clinic_id,
        "permissions": list(user_permissions)  # Convert set to list for JSON serialization
    }
    
    # Generate tokens
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)
    
    # Load clinic information
    query = select(User).options(selectinload(User.clinic)).where(User.id == user.id)
    result = await db.execute(query)
    user_with_clinic = result.scalar_one()
    
    # Prepare user response with role information
    user_dict = {
        "id": user_with_clinic.id,
        "username": user_with_clinic.username,
        "email": user_with_clinic.email,
        "first_name": user_with_clinic.first_name,
        "last_name": user_with_clinic.last_name,
        "role": user_with_clinic.role,
        "role_id": user_with_clinic.role_id,
        "role_name": user_role.name if user_role else None,
        "is_active": user_with_clinic.is_active,
        "is_verified": user_with_clinic.is_verified,
        "clinic_id": user_with_clinic.clinic_id,
        "clinic": user_with_clinic.clinic,
    }
    user_response = UserResponse.model_validate(user_dict)
    
    # Send login alert (background task, don't wait for it)
    try:
        # Get client IP and user agent
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        # Send alert in background (don't await)
        # Use asyncio.create_task to run in background
        import asyncio
        asyncio.create_task(send_login_alert(
            user_id=user.id,
            login_ip=client_ip,
            user_agent=user_agent,
            db=db
        ))
    except Exception as e:
        # Don't fail login if alert fails
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send login alert: {str(e)}")
    
    # Convert menu structure to response format (using dict to match schema)
    menu_response = []
    for group in menu_structure:
        menu_items = [
            {
                "id": item["id"],
                "group_id": group["id"],
                "name": item["name"],
                "route": item["route"],
                "icon": item.get("icon"),
                "order_index": item["order_index"],
                "description": item.get("description"),
                "badge": item.get("badge"),
                "is_external": item.get("is_external", False),
                "permissions_required": item.get("permissions_required"),
                "is_active": True
            }
            for item in group["items"]
        ]
        menu_response.append({
            "id": group["id"],
            "name": group["name"],
            "description": group.get("description"),
            "order_index": group["order_index"],
            "icon": group.get("icon"),
            "items": menu_items
        })
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_response,
        menu=menu_response,
        permissions=list(user_permissions)
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    User Registration Endpoint
    
    Creates a new user account.
    
    Args:
        user_data: User registration data
        db: Database session
        
    Returns:
        Created user data
        
    Raises:
        HTTPException: If username/email already exists
    """
    # Check if username already exists
    query = select(User).where(User.username == user_data.username)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    query = select(User).where(User.email == user_data.email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        role=user_data.role,
        clinic_id=user_data.clinic_id,
        is_active=True,
        is_verified=False
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    # Load clinic information to avoid lazy loading issues
    query = select(User).options(selectinload(User.clinic)).where(User.id == new_user.id)
    result = await db.execute(query)
    user_with_clinic = result.scalar_one()
    
    return UserResponse.model_validate(user_with_clinic)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get Current User Information
    
    Returns the currently authenticated user's data.
    
    Args:
        current_user: Current authenticated user from JWT token
        db: Database session
        
    Returns:
        Current user data with clinic information and role details
    """
    # Load clinic information
    query = select(User).options(selectinload(User.clinic)).where(User.id == current_user.id)
    result = await db.execute(query)
    user_with_clinic = result.scalar_one()
    
    # Get role information from menu service
    from app.services.menu_service import MenuService
    menu_service = MenuService(db)
    user_role = await menu_service.get_user_role(user_with_clinic.id)
    
    # Create user response with role information
    user_dict = {
        "id": user_with_clinic.id,
        "username": user_with_clinic.username,
        "email": user_with_clinic.email,
        "first_name": user_with_clinic.first_name,
        "last_name": user_with_clinic.last_name,
        "role": user_with_clinic.role,
        "role_id": user_with_clinic.role_id,
        "role_name": user_role.name if user_role else None,
        "is_active": user_with_clinic.is_active,
        "is_verified": user_with_clinic.is_verified,
        "clinic_id": user_with_clinic.clinic_id,
        "clinic": user_with_clinic.clinic,
    }
    
    return UserResponse.model_validate(user_dict)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    current_user: User = Depends(get_current_user)
):
    """
    Refresh Access Token
    
    Generates a new access token for the current user.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        New access token
    """
    token_data = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role.value,
        "clinic_id": current_user.clinic_id
    }
    
    access_token = create_access_token(data=token_data)
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    current_user: User = Depends(get_current_user)
):
    """
    User Logout
    
    Logout endpoint (client should discard the token).
    In a production system, you might want to implement token blacklisting.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Success message
    """
    return MessageResponse(message="Successfully logged out")


@router.get("/verify-token", response_model=UserResponse)
async def verify_token_endpoint(
    current_user: User = Depends(get_current_user)
):
    """
    Verify Token Validity
    
    Checks if the provided token is valid and returns user data.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User data if token is valid
    """
    return UserResponse.model_validate(current_user)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request_data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    """
    Request Password Reset
    
    Sends a password reset email to the user if the email exists.
    For security, always returns success even if email doesn't exist.
    
    Args:
        request_data: Email address
        db: Database session
        
    Returns:
        Success message
    """
    from app.models.password_reset import PasswordResetToken
    from app.schemas.auth import ForgotPasswordRequest
    from datetime import datetime, timedelta, timezone
    import secrets
    import hashlib
    
    # Find user by email
    query = select(User).where(User.email == request_data.email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    # Always return success for security (don't reveal if email exists)
    if not user:
        return MessageResponse(message="If the email exists, a password reset link has been sent.")
    
    # Generate secure token
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Set expiration (1 hour from now)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    # Invalidate any existing tokens for this user
    existing_tokens_query = select(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False
    )
    existing_tokens_result = await db.execute(existing_tokens_query)
    for existing_token in existing_tokens_result.scalars().all():
        existing_token.used = True
    
    # Create new reset token
    reset_token = PasswordResetToken(
        token=token_hash,
        user_id=user.id,
        expires_at=expires_at,
        used=False
    )
    db.add(reset_token)
    await db.commit()
    
    # Send email with reset link
    try:
        from app.services.email_service import email_service
        # Get frontend URL from CORS origins (first one if multiple)
        frontend_url = settings.BACKEND_CORS_ORIGINS.split(',')[0].strip() if ',' in settings.BACKEND_CORS_ORIGINS else settings.BACKEND_CORS_ORIGINS.strip()
        reset_url = f"{frontend_url}/reset-password?token={token}"
        
        email_body = f"""
        <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>Hello {user.first_name or user.username},</p>
            <p>You requested to reset your password. Click the link below to reset it:</p>
            <p><a href="{reset_url}" style="background-color: #7C3AED; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Reset Password</a></p>
            <p>Or copy and paste this link into your browser:</p>
            <p>{reset_url}</p>
            <p>This link will expire in 1 hour.</p>
            <p>If you didn't request this, please ignore this email.</p>
        </body>
        </html>
        """
        
        await email_service.send_email(
            to_email=user.email,
            subject="Password Reset Request - Prontivus",
            html_content=email_body
        )
    except Exception as e:
        # Log error but don't fail the request
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send password reset email: {str(e)}")
    
    return MessageResponse(message="If the email exists, a password reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request_data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Reset Password with Token
    
    Resets the user's password using a valid reset token.
    
    Args:
        request_data: Reset token and new password
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    from app.models.password_reset import PasswordResetToken
    from app.schemas.auth import ResetPasswordRequest
    import hashlib
    from datetime import datetime, timezone
    
    # Hash the provided token to compare with stored hash
    token_hash = hashlib.sha256(request_data.token.encode()).hexdigest()
    
    # Find the reset token
    query = select(PasswordResetToken).where(PasswordResetToken.token == token_hash)
    result = await db.execute(query)
    reset_token = result.scalar_one_or_none()
    
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Check if token is used
    if reset_token.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset token has already been used"
        )
    
    # Check if token is expired
    if datetime.now(timezone.utc) > reset_token.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new one."
        )
    
    # Get user
    user_query = select(User).where(User.id == reset_token.user_id)
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password
    user.hashed_password = hash_password(request_data.new_password)
    
    # Mark token as used
    reset_token.used = True
    
    try:
        await db.commit()
        return MessageResponse(message="Password has been reset successfully. You can now login with your new password.")
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset password: {str(e)}"
        )


@router.get("/google/authorize")
async def google_authorize(
    role: Optional[str] = Query(None, description="User role (patient or staff)"),
    redirect_uri: Optional[str] = Query(None, description="Frontend redirect URI")
):
    """
    Get Google OAuth Authorization URL
    
    Returns the Google OAuth authorization URL for the user to authenticate.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured"
        )
    
    # Build Google OAuth URL
    from urllib.parse import urlencode
    
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri or settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    
    if role:
        params["state"] = f"role={role}"
    
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    
    return {"auth_url": auth_url}


@router.get("/google/callback")
async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="State parameter"),
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    """
    Google OAuth Callback
    
    Handles the OAuth callback from Google, creates or logs in the user.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured"
        )
    
    try:
        # Exchange authorization code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            
            if token_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to exchange authorization code"
                )
            
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            
            if not access_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No access token received from Google"
                )
            
            # Get user info from Google
            user_info_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            
            if user_info_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user info from Google"
                )
            
            google_user = user_info_response.json()
            google_email = google_user.get("email")
            google_name = google_user.get("name", "")
            google_given_name = google_user.get("given_name", "")
            google_family_name = google_user.get("family_name", "")
            google_picture = google_user.get("picture")
            
            if not google_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email not provided by Google"
                )
            
            # Parse expected role from state if provided
            expected_role_str = None
            if state and "role=" in state:
                expected_role_str = state.split("role=")[1].split("&")[0]
            
            # Determine role for new users
            role = UserRole.PATIENT  # Default to patient
            if expected_role_str:
                if expected_role_str.lower() == "staff":
                    role = UserRole.SECRETARY  # Default staff role to secretary
                elif expected_role_str.lower() == "patient":
                    role = UserRole.PATIENT
            
            # Check if user exists by email
            query = select(User).where(User.email == google_email)
            result = await db.execute(query)
            user = result.scalar_one_or_none()
            
            # If user exists, verify role matches expected role
            if user and expected_role_str:
                expected_role = expected_role_str.lower()
                user_role = user.role.value.lower()
                
                if expected_role == "staff":
                    # Staff roles: admin, secretary, doctor
                    if user_role not in ["admin", "secretary", "doctor"]:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied. This login is restricted to staff members only."
                        )
                elif expected_role == "patient":
                    # Patient role only
                    if user_role != "patient":
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied. This login is restricted to patients only."
                        )
            
            # If user doesn't exist, create a new one
            if not user:
                # Generate username from email
                username = google_email.split("@")[0]
                # Ensure username is unique
                base_username = username
                counter = 1
                while True:
                    check_query = select(User).where(User.username == username)
                    check_result = await db.execute(check_query)
                    if not check_result.scalar_one_or_none():
                        break
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # Get default clinic (clinic_id = 1) or create logic for clinic assignment
                # For now, we'll use clinic_id = 1 as default
                # In production, you might want to have a clinic selection step
                default_clinic_id = 1
                
                # Try to get a clinic, if none exists, we'll need to handle this
                from app.models import Clinic
                clinic_query = select(Clinic).where(Clinic.id == default_clinic_id)
                clinic_result = await db.execute(clinic_query)
                clinic = clinic_result.scalar_one_or_none()
                
                if not clinic:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No clinic available. Please contact administrator."
                    )
                
                # Create new user
                user = User(
                    username=username,
                    email=google_email,
                    hashed_password="",  # OAuth users don't have passwords
                    first_name=google_given_name or google_name.split()[0] if google_name else None,
                    last_name=google_family_name or " ".join(google_name.split()[1:]) if google_name and len(google_name.split()) > 1 else None,
                    role=role,
                    clinic_id=default_clinic_id,
                    is_active=True,
                    is_verified=True,  # Google verified emails are considered verified
                )
                
                db.add(user)
                await db.commit()
                await db.refresh(user)
            
            # Load clinic information
            query = select(User).options(selectinload(User.clinic)).where(User.id == user.id)
            result = await db.execute(query)
            user_with_clinic = result.scalar_one()
            
            # Create tokens
            token_data = {
                "user_id": user.id,
                "username": user.username,
                "role": user.role.value,
                "clinic_id": user.clinic_id
            }
            
            access_token_jwt = create_access_token(data=token_data)
            refresh_token_jwt = create_refresh_token(data=token_data)
            
            # Prepare user response
            user_response = UserResponse.model_validate(user_with_clinic)
            
            # Send login alert (background task)
            try:
                client_ip = request.client.host if request.client else None
                user_agent = request.headers.get("user-agent")
                import asyncio
                asyncio.create_task(send_login_alert(
                    user_id=user.id,
                    login_ip=client_ip,
                    user_agent=user_agent,
                    db=db
                ))
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send login alert: {str(e)}")
            
            # Return redirect with tokens in query params (frontend will handle)
            # In production, you might want to use a more secure method
            frontend_url = settings.BACKEND_CORS_ORIGINS.split(",")[0] if "," in settings.BACKEND_CORS_ORIGINS else settings.BACKEND_CORS_ORIGINS
            # URL encode the user JSON
            import urllib.parse
            user_json_encoded = urllib.parse.quote(user_response.model_dump_json())
            redirect_url = f"{frontend_url}/auth/google/callback?token={access_token_jwt}&refresh_token={refresh_token_jwt or ''}&user={user_json_encoded}"
            
            return RedirectResponse(url=redirect_url)
            
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Google OAuth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth authentication failed: {str(e)}"
        )


"""
Authentication Endpoints
Handles user authentication, registration, and token management
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import get_db
from app.core.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password
)
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    TokenResponse,
    RegisterRequest,
    MessageResponse
)
from config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
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
    
    # Create token data
    token_data = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role.value,
        "clinic_id": user.clinic_id
    }
    
    # Generate tokens
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)
    
    # Load clinic information
    query = select(User).options(selectinload(User.clinic)).where(User.id == user.id)
    result = await db.execute(query)
    user_with_clinic = result.scalar_one()
    
    # Prepare user response
    user_response = UserResponse.model_validate(user_with_clinic)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_response
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
    
    return UserResponse.model_validate(new_user)


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
        Current user data with clinic information
    """
    # Load clinic information
    query = select(User).options(selectinload(User.clinic)).where(User.id == current_user.id)
    result = await db.execute(query)
    user_with_clinic = result.scalar_one()
    
    return UserResponse.model_validate(user_with_clinic)


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


"""
Authentication and Authorization Module
Handles password hashing, JWT token generation/verification, and user authentication
"""

from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from database import get_db
from app.models import User, UserRole
from app.core.security import (
    hash_password as secure_hash_password,
    verify_password as secure_verify_password,
    create_access_token as secure_create_access_token,
    create_refresh_token as secure_create_refresh_token,
    verify_token as secure_verify_token
)
from app.core.logging import security_logger

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token scheme
security = HTTPBearer()


# ==================== Password Hashing ====================

def hash_password(password: str) -> str:
    """
    Hash a plain text password using bcrypt
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string
    """
    return secure_hash_password(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password
    
    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password from database
        
    Returns:
        True if password matches, False otherwise
    """
    return secure_verify_password(plain_password, hashed_password)


# ==================== JWT Token Management ====================

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token
    
    Args:
        data: Dictionary containing user data (user_id, role, clinic_id)
        expires_delta: Optional expiration time delta
        
    Returns:
        Encoded JWT token string
    """
    return secure_create_access_token(data, expires_delta)


def create_refresh_token(data: dict) -> str:
    """
    Create a JWT refresh token with longer expiration
    
    Args:
        data: Dictionary containing user data
        
    Returns:
        Encoded JWT refresh token string
    """
    return secure_create_refresh_token(data)


def verify_token(token: str) -> dict:
    """
    Verify and decode a JWT token
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    return secure_verify_token(token)


async def get_current_user_from_token(token: str) -> User:
    """
    Get current user from JWT token (for middleware use)
    
    Args:
        token: JWT token string
        
    Returns:
        User object
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    from database import get_async_session
    
    payload = verify_token(token)
    user_id = payload.get("sub")
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    async for db in get_async_session():
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user


# ==================== User Authentication ====================

async def authenticate_user(
    db: AsyncSession,
    username_or_email: str,
    password: str
) -> Optional[User]:
    """
    Authenticate a user by username/email and password
    
    Args:
        db: Database session
        username_or_email: Username or email address
        password: Plain text password
        
    Returns:
        User object if authentication successful, None otherwise
    """
    # Query user by username or email
    query = select(User).where(
        (User.username == username_or_email) | 
        (User.email == username_or_email)
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        return None
    
    if not verify_password(password, user.hashed_password):
        return None
    
    if not user.is_active:
        return None
    
    return user


# ==================== Dependencies ====================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT token
    
    Args:
        credentials: HTTP Bearer credentials from request header
        db: Database session
        
    Returns:
        Current authenticated User object
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials
    
    try:
        payload = verify_token(token)
        user_id: int = payload.get("user_id")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database with clinic relationship
    from sqlalchemy.orm import selectinload
    query = select(User).options(selectinload(User.clinic)).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to ensure current user is active
    
    Args:
        current_user: Current user from get_current_user dependency
        
    Returns:
        Active User object
        
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


# ==================== Role-Based Access Control ====================

class RoleChecker:
    """
    Dependency class to check if user has required roles
    """
    
    def __init__(self, allowed_roles: list[UserRole]):
        """
        Initialize role checker with allowed roles
        
        Args:
            allowed_roles: List of UserRole enums that are allowed
        """
        self.allowed_roles = allowed_roles
    
    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        """
        Check if current user has one of the allowed roles
        
        Args:
            current_user: Current authenticated user
            
        Returns:
            User object if role is allowed
            
        Raises:
            HTTPException: If user doesn't have required role
        """
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {[role.value for role in self.allowed_roles]}"
            )
        return current_user


# Convenience functions for common role checks
def require_admin():
    """Require admin role"""
    return RoleChecker([UserRole.ADMIN])


def require_admin_or_secretary():
    """Require admin or secretary role"""
    return RoleChecker([UserRole.ADMIN, UserRole.SECRETARY])


def require_admin_or_doctor():
    """Require admin or doctor role"""
    return RoleChecker([UserRole.ADMIN, UserRole.DOCTOR])


def require_staff():
    """Require any staff role (admin, secretary, or doctor)"""
    return RoleChecker([UserRole.ADMIN, UserRole.SECRETARY, UserRole.DOCTOR])


# ==================== Optional Authentication ====================

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Optional authentication - returns user if token is provided and valid, None otherwise
    Useful for endpoints that have different behavior for authenticated vs anonymous users
    
    Args:
        credentials: Optional HTTP Bearer credentials
        db: Database session
        
    Returns:
        User object if authenticated, None otherwise
    """
    if credentials is None:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


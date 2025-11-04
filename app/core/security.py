"""
Enhanced security configuration and utilities
"""

import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Rate limiting storage (in production, use Redis)
login_attempts: Dict[str, Dict[str, Any]] = {}

# Security constants
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15
PASSWORD_RESET_EXPIRE_HOURS = 1


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
        "jti": generate_secure_token(16)  # JWT ID for token tracking
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
        "jti": generate_secure_token(16)
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt


def verify_token(token: str) -> Dict[str, Any]:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        
        # Check token type
        if payload.get("type") not in ["access", "refresh"]:
            raise JWTError("Invalid token type")
        
        # Check expiration
        if datetime.utcnow() > datetime.fromtimestamp(payload.get("exp", 0)):
            raise JWTError("Token expired")
        
        return payload
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def check_login_attempts(identifier: str) -> bool:
    """Check if login attempts are within limits"""
    now = datetime.utcnow()
    
    if identifier not in login_attempts:
        return True
    
    attempts = login_attempts[identifier]
    
    # Check if locked out
    if attempts.get("locked_until") and now < attempts["locked_until"]:
        return False
    
    # Reset if lockout period has passed
    if attempts.get("locked_until") and now >= attempts["locked_until"]:
        login_attempts[identifier] = {"count": 0, "last_attempt": None, "locked_until": None}
        return True
    
    # Check attempt count
    return attempts.get("count", 0) < MAX_LOGIN_ATTEMPTS


def record_login_attempt(identifier: str, success: bool) -> None:
    """Record a login attempt"""
    now = datetime.utcnow()
    
    if identifier not in login_attempts:
        login_attempts[identifier] = {"count": 0, "last_attempt": None, "locked_until": None}
    
    attempts = login_attempts[identifier]
    
    if success:
        # Reset on successful login
        login_attempts[identifier] = {"count": 0, "last_attempt": None, "locked_until": None}
    else:
        # Increment failed attempts
        attempts["count"] = attempts.get("count", 0) + 1
        attempts["last_attempt"] = now
        
        # Lock account if max attempts reached
        if attempts["count"] >= MAX_LOGIN_ATTEMPTS:
            attempts["locked_until"] = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)


def create_password_reset_token(email: str) -> str:
    """Create a password reset token"""
    data = {
        "email": email,
        "type": "password_reset",
        "exp": datetime.utcnow() + timedelta(hours=PASSWORD_RESET_EXPIRE_HOURS)
    }
    
    return jwt.encode(
        data,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )


def verify_password_reset_token(token: str) -> str:
    """Verify a password reset token and return email"""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        
        if payload.get("type") != "password_reset":
            raise JWTError("Invalid token type")
        
        return payload.get("email")
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )


def get_password_strength_score(password: str) -> int:
    """Calculate password strength score (0-100)"""
    score = 0
    
    # Length bonus
    if len(password) >= 8:
        score += 20
    if len(password) >= 12:
        score += 10
    if len(password) >= 16:
        score += 10
    
    # Character variety
    if any(c.islower() for c in password):
        score += 10
    if any(c.isupper() for c in password):
        score += 10
    if any(c.isdigit() for c in password):
        score += 10
    if any(c in "!@#$%^&*(),.?\":{}|<>" for c in password):
        score += 20
    
    # Pattern penalties
    if password.lower() in ["password", "123456", "qwerty"]:
        score = 0
    
    return min(score, 100)

"""
Security middleware for authentication, logging, and rate limiting
"""

import time
from typing import Callable
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging import security_logger, get_client_ip
from app.core.security import check_login_attempts, record_login_attempt


class SecurityMiddleware(BaseHTTPMiddleware):
    """Security middleware for logging and rate limiting"""
    
    def __init__(self, app, rate_limit_requests: int = 100, rate_limit_window: int = 60):
        super().__init__(app)
        self.rate_limit_requests = rate_limit_requests
        self.rate_limit_window = rate_limit_window
        self.rate_limit_storage = {}  # In production, use Redis
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Start timing
        start_time = time.time()
        
        # Get client IP
        client_ip = get_client_ip(request)
        
        # Rate limiting
        if not self._check_rate_limit(client_ip):
            security_logger.log_security_event(
                event_type="rate_limit_exceeded",
                user_id=None,
                username=None,
                ip_address=client_ip,
                description=f"Rate limit exceeded for IP {client_ip}",
                severity="WARNING"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded. Please try again later."}
            )
        
        # Process request
        try:
            response = await call_next(request)
            processing_time = time.time() - start_time
            
            # Log API access
            security_logger.log_api_access(
                request=request,
                user_id=None,  # Will be filled by auth middleware
                username=None,
                response_status=response.status_code,
                processing_time=processing_time
            )
            
            return response
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # Log error
            security_logger.log_security_event(
                event_type="api_error",
                user_id=None,
                username=None,
                ip_address=client_ip,
                description=f"API error: {str(e)}",
                severity="ERROR",
                additional_data={
                    "url": str(request.url),
                    "method": request.method,
                    "processing_time": processing_time
                }
            )
            
            raise
    
    def _check_rate_limit(self, client_ip: str) -> bool:
        """Check if client is within rate limits"""
        now = time.time()
        window_start = now - self.rate_limit_window
        
        # Clean old entries
        if client_ip in self.rate_limit_storage:
            self.rate_limit_storage[client_ip] = [
                timestamp for timestamp in self.rate_limit_storage[client_ip]
                if timestamp > window_start
            ]
        else:
            self.rate_limit_storage[client_ip] = []
        
        # Check if under limit
        if len(self.rate_limit_storage[client_ip]) >= self.rate_limit_requests:
            return False
        
        # Add current request
        self.rate_limit_storage[client_ip].append(now)
        return True


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware to add user context to requests"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract user info from JWT if present
        user_id = None
        username = None
        
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from app.core.auth import get_current_user_from_token
                token = auth_header.split(" ")[1]
                user = await get_current_user_from_token(token)
                user_id = user.id
                username = user.username
            except:
                pass  # Invalid token, continue without user context
        
        # Add user context to request state
        request.state.user_id = user_id
        request.state.username = username
        
        response = await call_next(request)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Content Security Policy (allow dev frontends to connect to API)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' http://localhost:3000 http://127.0.0.1:3000 http://localhost:8000 http://127.0.0.1:8000 ws://localhost:* ws://127.0.0.1:*; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Content-Security-Policy"] = csp
        
        return response


class LoginAttemptMiddleware(BaseHTTPMiddleware):
    """Middleware to track and limit login attempts"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check if this is a login endpoint
        if request.url.path.endswith("/login") and request.method == "POST":
            client_ip = get_client_ip(request)
            
            # Check if IP is locked out
            if not check_login_attempts(client_ip):
                security_logger.log_security_event(
                    event_type="login_blocked",
                    user_id=None,
                    username=None,
                    ip_address=client_ip,
                    description=f"Login blocked for IP {client_ip} due to too many attempts",
                    severity="WARNING"
                )
                
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many login attempts. Please try again later."}
                )
        
        response = await call_next(request)
        
        # Record login attempt result
        if request.url.path.endswith("/login") and request.method == "POST":
            client_ip = get_client_ip(request)
            success = response.status_code == 200
            
            # Extract username from request body if possible
            username = "unknown"
            try:
                body = await request.body()
                import json
                data = json.loads(body)
                username = data.get("username_or_email", "unknown")
            except:
                pass
            
            # Record the attempt
            record_login_attempt(client_ip, success)
            
            # Log the attempt
            security_logger.log_login_attempt(
                username=username,
                ip_address=client_ip,
                user_agent=request.headers.get("user-agent", ""),
                success=success,
                failure_reason=None if success else "Invalid credentials",
                user_id=None
            )
        
        return response

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn
import traceback
import os
import json

# Import API routers
from app.api.endpoints import auth, patients, appointments, users, clinical, financial, tiss, tiss_batch, tiss_templates, stock, procedures, analytics, admin, licenses, voice, migration, files, patient_calling, websocket_calling, notifications, user_settings, tiss_config, messages, menu, rbac_test, patient_dashboard, secretary_dashboard, doctor_dashboard, ai_config, ai_usage, fiscal_config, reports, payment_methods, report_config, support
from app.api.endpoints import icd10

# Import security middleware
from app.core.middleware import SecurityMiddleware, AuthenticationMiddleware, SecurityHeadersMiddleware, LoginAttemptMiddleware
from app.middleware.licensing import licensing_middleware

# Import monitoring and caching
from app.core.monitoring import init_sentry
from app.core.cache import cache_manager

# Get CORS origins from environment variable
def get_cors_origins():
    """Get CORS origins from environment variable or use defaults"""
    cors_env = os.getenv("BACKEND_CORS_ORIGINS", "")
    if cors_env:
        # Split by comma and strip whitespace
        origins = [origin.strip() for origin in cors_env.split(",")]
        return origins
    # Default origins for development
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup: Initialize monitoring and caching
    print("🚀 Prontivus API starting up...")
    
    # Initialize Sentry for error tracking
    if init_sentry():
        print("✅ Sentry monitoring initialized")
    
    # Connect to Redis cache
    await cache_manager.connect()
    if cache_manager.enabled:
        print("✅ Redis cache connected")
    
    yield
    
    # Shutdown: Close connections
    await cache_manager.disconnect()
    print("👋 Prontivus API shutting down...")

# Initialize FastAPI app
app = FastAPI(
    title="Prontivus API",
    description="Healthcare Management System API",
    version="1.0.0",
    lifespan=lifespan
)
# Configure CORS FIRST so headers are present even on errors
cors_origins = get_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+" if os.getenv("ENVIRONMENT") == "development" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Authorization", "X-Request-Id"],
)

# Add security middleware (order matters!)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LoginAttemptMiddleware)
app.add_middleware(AuthenticationMiddleware)
app.add_middleware(SecurityMiddleware, rate_limit_requests=100, rate_limit_window=60)

# Add licensing middleware after authentication (function-style middleware)
app.middleware("http")(licensing_middleware)

# Exception handler for HTTPException to ensure CORS headers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTPException with CORS headers"""
    origin = request.headers.get("origin")
    allowed_origins = get_cors_origins()
    
    # Check if origin is allowed
    is_allowed = False
    if origin:
        if origin in allowed_origins:
            is_allowed = True
        elif os.getenv("ENVIRONMENT") == "development":
            # In development, allow localhost origins
            if origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:"):
                is_allowed = True
    
    if is_allowed:
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
        # Merge with any existing headers from the exception
        if hasattr(exc, 'headers') and exc.headers:
            headers.update(exc.headers)
    else:
        headers = exc.headers if hasattr(exc, 'headers') and exc.headers else {}
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers
    )

# Global exception handler to ensure CORS headers are always present
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler that ensures CORS headers are present on all error responses"""
    origin = request.headers.get("origin")
    allowed_origins = get_cors_origins()
    
    # Check if origin is allowed
    is_allowed = False
    if origin:
        if origin in allowed_origins:
            is_allowed = True
        elif os.getenv("ENVIRONMENT") == "development":
            # In development, allow localhost origins
            if origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:"):
                is_allowed = True
    
    if is_allowed:
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    else:
        headers = {}
    
    # Log the error
    error_detail = str(exc)
    if hasattr(exc, 'detail'):
        error_detail = exc.detail
    elif hasattr(exc, 'msg'):
        error_detail = exc.msg
    
    # In development, include traceback
    if os.getenv("ENVIRONMENT", "development") == "development":
        traceback_str = traceback.format_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": error_detail,
                "type": type(exc).__name__,
                "traceback": traceback_str.split("\n") if traceback_str else None
            },
            headers=headers
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
            headers=headers
        )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with CORS headers"""
    origin = request.headers.get("origin")
    allowed_origins = get_cors_origins()
    
    # Check if origin is allowed
    is_allowed = False
    if origin:
        if origin in allowed_origins:
            is_allowed = True
        elif os.getenv("ENVIRONMENT") == "development":
            # In development, allow localhost origins
            if origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:"):
                is_allowed = True
    
    if is_allowed:
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    else:
        headers = {}
    
    # Convert errors to serializable format
    def make_serializable(obj):
        """Recursively convert non-serializable objects to strings"""
        if isinstance(obj, (Exception, BaseException)):
            return str(obj)
        elif isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [make_serializable(item) for item in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            # Try to serialize, if fails convert to string
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)
    
    try:
        errors = exc.errors()
        serializable_errors = [make_serializable(error) for error in errors]
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": serializable_errors},
            headers=headers
        )
    except Exception as e:
        # Fallback: return a simple error message if serialization fails
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": [{"msg": "Validation error", "type": "value_error"}]},
            headers=headers
        )

# Mount static files for avatars and uploads
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
if os.path.exists(STORAGE_DIR):
    app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage")

# Include API routers with versioning
# API Version 1 - All endpoints under /api/v1
# Note: Register clinical router BEFORE appointments router to ensure
# specific routes like /appointments/{id}/clinical-record are matched correctly
API_V1_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_V1_PREFIX, tags=["Authentication"])
app.include_router(patients.router, prefix=API_V1_PREFIX, tags=["Patients"])
app.include_router(clinical.router, prefix=API_V1_PREFIX, tags=["Clinical"])
app.include_router(appointments.router, prefix=API_V1_PREFIX, tags=["Appointments"])
app.include_router(users.router, prefix=API_V1_PREFIX, tags=["Users"])
app.include_router(financial.router, prefix=f"{API_V1_PREFIX}/financial", tags=["Financial"])
app.include_router(tiss.router, prefix=API_V1_PREFIX, tags=["TISS"])
app.include_router(tiss_templates.router, prefix=f"{API_V1_PREFIX}/financial", tags=["TISS Templates"])
app.include_router(tiss_batch.router, prefix=API_V1_PREFIX, tags=["TISS Batch"])
app.include_router(stock.router, prefix=API_V1_PREFIX, tags=["Stock"])
app.include_router(procedures.router, prefix=API_V1_PREFIX, tags=["Procedures"])
app.include_router(analytics.router, prefix=API_V1_PREFIX, tags=["Analytics"])
app.include_router(admin.router, prefix=API_V1_PREFIX, tags=["Admin"])
app.include_router(licenses.router, prefix=API_V1_PREFIX, tags=["Licenses"])
app.include_router(ai_config.router, prefix=API_V1_PREFIX, tags=["AI Configuration"])
app.include_router(ai_usage.router, prefix=API_V1_PREFIX, tags=["AI Usage"])
app.include_router(fiscal_config.router, prefix=API_V1_PREFIX, tags=["Fiscal Configuration"])
app.include_router(reports.router, prefix=API_V1_PREFIX, tags=["Reports"])
app.include_router(icd10.router, prefix=API_V1_PREFIX, tags=["ICD-10"])
app.include_router(voice.router, prefix=API_V1_PREFIX, tags=["Voice"])
app.include_router(migration.router, prefix=API_V1_PREFIX, tags=["Migration"])
app.include_router(files.router, prefix=API_V1_PREFIX, tags=["Files"])
app.include_router(patient_calling.router, prefix=API_V1_PREFIX, tags=["Patient Calling"])
app.include_router(websocket_calling.router, tags=["WebSocket Calling"])
app.include_router(notifications.router, prefix=API_V1_PREFIX, tags=["Notifications"])
app.include_router(tiss_config.router, prefix=f"{API_V1_PREFIX}/financial", tags=["TISS Config"])
app.include_router(user_settings.router, prefix=API_V1_PREFIX, tags=["User Settings"])
app.include_router(messages.router, prefix=API_V1_PREFIX, tags=["Messages"])
app.include_router(menu.router, prefix=API_V1_PREFIX, tags=["Menu Management"])
app.include_router(rbac_test.router, prefix=API_V1_PREFIX, tags=["RBAC Testing"])
app.include_router(patient_dashboard.router, prefix=API_V1_PREFIX, tags=["Patient Dashboard"])
app.include_router(secretary_dashboard.router, prefix=API_V1_PREFIX, tags=["Secretary Dashboard"])
app.include_router(doctor_dashboard.router, prefix=API_V1_PREFIX, tags=["Doctor Dashboard"])
app.include_router(payment_methods.router, prefix=API_V1_PREFIX, tags=["Payment Methods"])
app.include_router(report_config.router, prefix=API_V1_PREFIX, tags=["Report Config"])
app.include_router(support.router, prefix=API_V1_PREFIX, tags=["Support"])

# Legacy /api routes for backward compatibility (deprecated)
# TODO: Remove in v2.0.0
app.include_router(auth.router, prefix="/api", tags=["Authentication (Legacy)"], deprecated=True)
app.include_router(patients.router, prefix="/api", tags=["Patients (Legacy)"], deprecated=True)
app.include_router(clinical.router, prefix="/api", tags=["Clinical (Legacy)"], deprecated=True)
app.include_router(appointments.router, prefix="/api", tags=["Appointments (Legacy)"], deprecated=True)
app.include_router(users.router, prefix="/api", tags=["Users (Legacy)"], deprecated=True)
app.include_router(financial.router, prefix="/api/financial", tags=["Financial (Legacy)"], deprecated=True)
app.include_router(tiss.router, prefix="/api", tags=["TISS (Legacy)"], deprecated=True)
app.include_router(tiss_templates.router, prefix="/api/financial", tags=["TISS Templates (Legacy)"], deprecated=True)
app.include_router(tiss_batch.router, prefix="/api", tags=["TISS Batch (Legacy)"], deprecated=True)
app.include_router(stock.router, prefix="/api", tags=["Stock (Legacy)"], deprecated=True)
app.include_router(procedures.router, prefix="/api", tags=["Procedures (Legacy)"], deprecated=True)
app.include_router(analytics.router, prefix="/api", tags=["Analytics (Legacy)"], deprecated=True)
app.include_router(admin.router, prefix="/api", tags=["Admin (Legacy)"], deprecated=True)
app.include_router(licenses.router, prefix="/api", tags=["Licenses (Legacy)"], deprecated=True)
app.include_router(icd10.router, prefix="/api", tags=["ICD-10 (Legacy)"], deprecated=True)
app.include_router(voice.router, prefix="/api", tags=["Voice (Legacy)"], deprecated=True)
app.include_router(migration.router, prefix="/api", tags=["Migration (Legacy)"], deprecated=True)
app.include_router(files.router, prefix="/api", tags=["Files (Legacy)"], deprecated=True)
app.include_router(patient_calling.router, prefix="/api", tags=["Patient Calling (Legacy)"], deprecated=True)
app.include_router(notifications.router, prefix="/api", tags=["Notifications (Legacy)"], deprecated=True)
app.include_router(tiss_config.router, prefix="/api/financial", tags=["TISS Config (Legacy)"], deprecated=True)
app.include_router(user_settings.router, prefix="/api", tags=["User Settings (Legacy)"], deprecated=True)
app.include_router(messages.router, prefix="/api", tags=["Messages (Legacy)"], deprecated=True)
app.include_router(menu.router, prefix="/api", tags=["Menu Management (Legacy)"], deprecated=True)
app.include_router(patient_dashboard.router, prefix="/api", tags=["Patient Dashboard (Legacy)"], deprecated=True)
app.include_router(secretary_dashboard.router, prefix="/api", tags=["Secretary Dashboard (Legacy)"], deprecated=True)
app.include_router(doctor_dashboard.router, prefix="/api", tags=["Doctor Dashboard (Legacy)"], deprecated=True)
app.include_router(payment_methods.router, prefix="/api", tags=["Payment Methods (Legacy)"], deprecated=True)
app.include_router(report_config.router, prefix="/api", tags=["Report Config (Legacy)"], deprecated=True)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.get("/favicon.ico")
async def favicon():
    """Return empty favicon to avoid 404 errors"""
    from fastapi.responses import Response
    return Response(status_code=204)

@app.get("/api/health")
async def health_check():
    """Detailed health check endpoint"""
    return {
        "status": "healthy",
        "service": "Prontivus API",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )


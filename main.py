from fastapi import FastAPI, Request, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import uvicorn
import traceback

# Import API routers
from app.api.endpoints import auth, patients, appointments, users, clinical, financial, tiss, tiss_batch, tiss_templates, stock, procedures, analytics, admin, licenses, voice, migration, files, patient_calling, websocket_calling, notifications, user_settings, tiss_config
from app.api.endpoints import icd10

# Import security middleware
from app.core.middleware import SecurityMiddleware, AuthenticationMiddleware, SecurityHeadersMiddleware, LoginAttemptMiddleware
from app.middleware.licensing import licensing_middleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup: Can add database initialization here
    # For now, database tables should be created via Alembic migrations
    print("🚀 CliniCore API starting up...")
    yield
    # Shutdown: Close connections
    print("👋 CliniCore API shutting down...")

# Initialize FastAPI app
app = FastAPI(
    title="Prontivus API",
    description="Healthcare Management System API",
    version="1.0.0",
    lifespan=lifespan
)
# Configure CORS FIRST so headers are present even on errors
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
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
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    if origin and (origin in allowed_origins or origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")):
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
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    # Check if origin matches allowed patterns
    if origin and (origin in allowed_origins or origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")):
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
    import os
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
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    if origin and (origin in allowed_origins or origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")):
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    else:
        headers = {}
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
        headers=headers
    )

# Include API routers
# Note: Register clinical router BEFORE appointments router to ensure
# specific routes like /appointments/{id}/clinical-record are matched correctly
app.include_router(auth.router, prefix="/api")
app.include_router(patients.router, prefix="/api")
app.include_router(clinical.router, prefix="/api")
app.include_router(appointments.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(financial.router, prefix="/api/financial")
app.include_router(tiss.router, prefix="/api")
app.include_router(tiss_templates.router, prefix="/api/financial")
app.include_router(tiss_batch.router, prefix="/api")
app.include_router(stock.router, prefix="/api")
app.include_router(procedures.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(licenses.router, prefix="/api")
app.include_router(icd10.router, prefix="/api")
app.include_router(voice.router, prefix="/api")
app.include_router(migration.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(patient_calling.router, prefix="/api")
app.include_router(websocket_calling.router)
app.include_router(notifications.router, prefix="/api")
app.include_router(tiss_config.router, prefix="/api/financial")
app.include_router(user_settings.router, prefix="/api")

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


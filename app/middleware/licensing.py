"""
Licensing Middleware
Validates license status and entitlements with periodic revalidation and offline grace.
"""

import time
import random
from datetime import datetime, timezone, timedelta
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_async_session
from app.models import Clinic, License, Entitlement
from app.models.license import LicenseStatus
from app.core.logging import security_logger


_LAST_VALIDATION_CACHE = {}
_GRACE_SECONDS = 72 * 3600


async def licensing_middleware(request: Request, call_next):
    path = request.url.path
    if (
        path.startswith("/api/auth/")
        or path.startswith("/api/licenses/activate")
        or path.startswith("/api/analytics")
        or path in ("/", "/api/health")
    ):
        return await call_next(request)

    # Requires auth to have set clinic context
    clinic_id = getattr(request.state, "clinic_id", None) or getattr(request.state, "user_id", None)
    # Prefer explicit clinic_id on request.state set by auth layer
    clinic_id = getattr(request.state, "clinic_id", None)
    if clinic_id is None:
        # Fall back to token parsing not implemented here
        return await call_next(request)

    async with get_async_session() as db:
        # Fetch clinic and license
        q = await db.execute(select(Clinic).where(Clinic.id == clinic_id))
        clinic = q.scalar_one_or_none()
        if not clinic or not clinic.license_id:
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "No license for clinic"})

        lic_q = await db.execute(select(License).where(License.id == clinic.license_id))
        license_obj = lic_q.scalar_one_or_none()
        if not license_obj:
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "License not found"})

        # Periodic revalidation window 6-12 hours with jitter
        now = time.time()
        next_due = _LAST_VALIDATION_CACHE.get(str(clinic.id))
        if not next_due or now >= next_due:
            # Basic status/time window checks
            if license_obj.status not in (LicenseStatus.ACTIVE,):
                return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "License not active"})
            if license_obj.end_at and datetime.now(timezone.utc) > license_obj.end_at:
                return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "License expired"})

            # schedule next validation time
            hours = random.randint(6, 12)
            _LAST_VALIDATION_CACHE[str(clinic.id)] = now + hours * 3600

        # Offline grace logic: if DB/remote check fails we'd allow within grace window
        # (Here we assume DB is reachable; remote signature server not used in this build.)

        # Entitlement check: derive module from path prefix /api/{module}
        try:
            segments = [s for s in path.split('/') if s]
            module = segments[1] if len(segments) > 1 and segments[0] == 'api' else None
        except Exception:
            module = None
        if module:
            ent_q = await db.execute(select(Entitlement).where(Entitlement.license_id == license_obj.id, Entitlement.module == module))
            ent = ent_q.scalar_one_or_none()
            if not ent or not ent.enabled:
                return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": f"Module '{module}' not enabled"})

    return await call_next(request)

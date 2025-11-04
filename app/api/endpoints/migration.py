from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_async_session
from app.core.auth import get_current_user
from app.models import User
from app.models.migration import MigrationJob, MigrationStatus
from app.schemas.migration import MigrationJobCreate, MigrationJobResponse
from app.services.migration_service import create_job, run_job
from app.services.migration_reports import pre_migration_quality, post_migration_validation

router = APIRouter(prefix="/migration", tags=["Migration"])


@router.post("/jobs", response_model=MigrationJobResponse)
async def create_migration_job(payload: MigrationJobCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_session)):
    job = await create_job(db, current_user.clinic_id, current_user.id, payload.type, payload.input_format, payload.source_name, payload.params)
    await db.commit()
    return job


@router.post("/jobs/{job_id}/upload", response_model=MigrationJobResponse)
async def upload_migration_data(job_id: int, file: UploadFile = File(...), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_session)):
    res = await db.execute(select(MigrationJob).where(MigrationJob.id == job_id, MigrationJob.clinic_id == current_user.clinic_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    content = await file.read()
    try:
        # Pre-quality (best-effort)
        try:
            import json
            pre_records = []
            if job.input_format == 'json':
                pre_records = json.loads(content.decode('utf-8'))
                if isinstance(pre_records, dict):
                    pre_records = [pre_records]
            pre = pre_migration_quality(pre_records) if pre_records else None
        except Exception:
            pre = None

        imported, stats, errors = await run_job(db, job, content)
        # Post validation
        post = post_migration_validation(imported, stats)
        # Attach report
        job.stats = {**(job.stats or {}), 'pre_quality': pre, 'post_validation': post}
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    return job


@router.get("/jobs", response_model=list[MigrationJobResponse])
async def list_jobs(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_session)):
    res = await db.execute(select(MigrationJob).where(MigrationJob.clinic_id == current_user.clinic_id).order_by(MigrationJob.created_at.desc()))
    return res.scalars().all()


@router.post("/jobs/{job_id}/rollback", response_model=MigrationJobResponse)
async def rollback_job(job_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_session)):
    res = await db.execute(select(MigrationJob).where(MigrationJob.id == job_id, MigrationJob.clinic_id == current_user.clinic_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # TODO: implement domain-specific rollback. For now, mark status.
    job.status = MigrationStatus.ROLLED_BACK
    await db.commit()
    return job



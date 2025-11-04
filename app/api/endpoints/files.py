from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
import os

from database import get_async_session
from app.core.auth import get_current_user
from app.models import User
from app.models.file_upload import FileUpload
from app.schemas.file_upload import FileUploadResponse
from app.services.file_storage import validate_file, store_file

router = APIRouter(prefix="/files", tags=["Files"])

BASE_DIR = os.getenv("FILE_STORAGE_DIR", os.path.join("storage", "uploads"))


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    patient_id: int = Query(...),
    appointment_id: int | None = Query(None),
    exam_type: str | None = Query(None),
    exam_date: str | None = Query(None),
    laboratory: str | None = Query(None),
    observations: str | None = Query(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    content = await file.read()
    try:
        validate_file(file.filename, file.content_type or "", len(content))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    path = store_file(BASE_DIR, current_user.clinic_id, patient_id, file.filename, content)

    rec = FileUpload(
        patient_id=patient_id,
        appointment_id=appointment_id,
        filename=file.filename,
        stored_path=path,
        filetype=file.content_type or "",
        uploaded_by=current_user.id,
        exam_type=exam_type,
        laboratory=laboratory,
        observations=observations,
    )
    db.add(rec)
    await db.flush()
    await db.commit()
    return rec


@router.get("", response_model=list[FileUploadResponse])
async def list_files(
    patient_id: int | None = Query(None),
    exam_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    # RBAC: patients can only view their own files
    if getattr(current_user, "role", None) == "patient":
        # If caller passes a different patient_id, deny
        if patient_id is not None and patient_id != current_user.id:
            raise HTTPException(status_code=403, detail="Acesso negado")
        # Force patient_id to current user's id
        patient_id = current_user.id

    q = select(FileUpload)
    if patient_id is not None:
        q = q.where(FileUpload.patient_id == patient_id)
    if exam_type:
        q = q.where(FileUpload.exam_type == exam_type)

    try:
        res = await db.execute(q.order_by(FileUpload.upload_date.desc()))
        return res.scalars().all()
    except SQLAlchemyError:
        # If the table doesn't exist yet or any DB error occurs, avoid 500 and return empty
        await db.rollback()
        return []


@router.get("/{file_id}")
async def download_file(file_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_session)):
    res = await db.execute(select(FileUpload).where(FileUpload.id == file_id))
    f = res.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    # Access control
    if current_user.role == "patient" and f.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    # Doctors/staff of same clinic allowed (assumed by get_current_user)
    if not os.path.exists(f.stored_path):
        raise HTTPException(status_code=410, detail="Arquivo indisponível")
    # Simple audit log
    import logging
    logging.getLogger(__name__).info("file_access user=%s file_id=%s patient_id=%s", current_user.id, f.id, f.patient_id)
    from fastapi.responses import FileResponse
    return FileResponse(path=f.stored_path, media_type=f.filetype, filename=f.filename)



"""
ICD-10 endpoints: import from ZIP, search, and code lookup
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.auth import RoleChecker
from app.models import User, UserRole
from app.models.icd10 import (
    ICD10Chapter, ICD10Group, ICD10Category, ICD10Subcategory, ICD10SearchIndex
)
from app.schemas.icd10 import (
    ICD10ChapterResponse,
    ICD10GroupResponse,
    ICD10CategoryResponse,
    ICD10SubcategoryResponse,
    ICD10SearchResult,
)
from app.services.icd10_import import import_icd10_from_zip, normalize_text
from app.services.icd10_comprehensive_import import import_all_icd10_data
from database import get_async_session

router = APIRouter(prefix="/icd10", tags=["ICD-10"])

require_admin = RoleChecker([UserRole.ADMIN])
require_staff = RoleChecker([UserRole.ADMIN, UserRole.SECRETARY, UserRole.DOCTOR])


@router.post("/import")
async def import_icd10(
    zip_path: str = Query("CID10CSV.zip", description="Path to CID10CSV.zip"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Import ICD-10 data from a CSV ZIP package into the database.
    Default path expects the file at project root: CID10CSV.zip
    """
    try:
        results = await import_icd10_from_zip(db, zip_path)
        return {"imported": results}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="ZIP file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-all")
async def import_all_icd10(
    csv_path: str = Query("CID10CSV.zip", description="Path to CID10CSV.zip"),
    xml_path: str = Query("CID10XML.zip", description="Path to CID10XML.zip"),
    cnv_path: str = Query("CID10CNV.zip", description="Path to CID10CNV.zip"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Import all ICD-10 data from CSV, XML, and CNV packages into the database.
    This is the comprehensive import that processes all three data sources.
    """
    try:
        results = await import_all_icd10_data(db, csv_path, xml_path, cnv_path)
        return {"imported": results}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=List[ICD10SearchResult])
async def search_icd10(
    query: str = Query(..., min_length=1),
    level: Optional[str] = Query(None, regex="^(chapter|group|category|subcategory)$"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Search ICD-10 codes by normalized text. Optional filter by level.
    """
    q = select(ICD10SearchIndex).filter(
        ICD10SearchIndex.search_text.ilike(f"%{normalize_text(query)}%")
    )
    if level:
        q = q.filter(ICD10SearchIndex.level == level)
    q = q.limit(limit)
    results = (await db.execute(q)).scalars().all()
    return [
        ICD10SearchResult(
            code=r.code,
            description=r.description,
            level=r.level,
            parent_code=r.parent_code,
        ) for r in results
    ]


@router.get("/code/{code}")
async def get_icd10_code(
    code: str,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Lookup a specific code. Tries subcategory, category, then group and chapter.
    """
    code = code.upper()
    # Subcategory
    sub = (await db.execute(select(ICD10Subcategory).filter(ICD10Subcategory.code == code))).scalar_one_or_none()
    if sub:
        return ICD10SubcategoryResponse.model_validate(sub)
    # Category
    cat = (await db.execute(select(ICD10Category).filter(ICD10Category.code == code))).scalar_one_or_none()
    if cat:
        return ICD10CategoryResponse.model_validate(cat)
    # Group
    grp = (await db.execute(select(ICD10Group).filter(ICD10Group.code == code))).scalar_one_or_none()
    if grp:
        return ICD10GroupResponse.model_validate(grp)
    # Chapter
    ch = (await db.execute(select(ICD10Chapter).filter(ICD10Chapter.code == code))).scalar_one_or_none()
    if ch:
        return ICD10ChapterResponse.model_validate(ch)
    raise HTTPException(status_code=404, detail="Code not found")



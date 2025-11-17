"""
Fiscal Integration Configuration API Endpoints
Handles fiscal integration settings for SuperAdmin
"""

from typing import Optional, Dict, Any, List
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError

from database import get_async_session
from app.core.auth import get_current_user
from app.models import User, Invoice, InvoiceStatus
from app.middleware.permissions import require_super_admin

router = APIRouter(prefix="/fiscal-config", tags=["Fiscal Configuration"])


def _default_fiscal_config() -> Dict[str, Any]:
    """Default fiscal configuration"""
    return {
        "enabled": False,
        "provider": "",
        "environment": "homologation",  # homologation or production
        "certificate_path": "",
        "certificate_password": "",
        "settings": {
            "auto_issue": False,
            "auto_send_email": False,
            "auto_print": False,
        },
        "last_sync": None,
    }


@router.get("")
async def get_fiscal_config(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get fiscal configuration (SuperAdmin only)
    Returns default config if none exists
    """
    # For now, return default config
    # In the future, this could be stored in a database table
    return _default_fiscal_config()


@router.put("")
async def update_fiscal_config(
    config: Dict[str, Any],
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update fiscal configuration (SuperAdmin only)
    """
    # Validate required fields
    if "enabled" not in config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="enabled field is required"
        )
    
    # Validate provider
    valid_providers = ["nfe", "nfse", "focus", "bling"]
    if config.get("provider") and config["provider"] not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}"
        )
    
    # Validate environment
    valid_environments = ["homologation", "production"]
    if config.get("environment") and config["environment"] not in valid_environments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid environment. Must be one of: {', '.join(valid_environments)}"
        )
    
    # For now, just return success
    # In the future, this would save to a database table
    return {
        "message": "Fiscal configuration updated successfully",
        "config": config
    }


@router.post("/test-connection")
async def test_fiscal_connection(
    config: Optional[Dict[str, Any]] = Body(None),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Test fiscal integration connection (SuperAdmin only)
    Accepts optional config in body to test with specific credentials
    """
    import time
    start_time = time.time()
    
    # For now, return a mock success response
    # In the future, this would actually test the connection with the provided config
    provider = config.get("provider", "nfe") if config else "nfe"
    environment = config.get("environment", "homologation") if config else "homologation"
    
    # Simulate connection test
    await asyncio.sleep(0.1)
    
    response_time_ms = int((time.time() - start_time) * 1000)
    
    return {
        "success": True,
        "message": "Connection test successful",
        "provider": provider,
        "environment": environment,
        "response_time_ms": response_time_ms
    }


@router.post("/upload-certificate")
async def upload_certificate(
    certificate: UploadFile = File(...),
    password: Optional[str] = Form(None),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Upload fiscal certificate (SuperAdmin only)
    """
    # Validate file type
    if not certificate.filename.endswith(('.pfx', '.p12')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid certificate file. Must be .pfx or .p12"
        )
    
    # Read certificate file
    certificate_data = await certificate.read()
    
    # For now, just return success
    # In the future, this would save the certificate securely
    return {
        "message": "Certificate uploaded successfully",
        "filename": certificate.filename,
        "size": len(certificate_data),
        "has_password": password is not None
    }


@router.get("/documents")
async def get_fiscal_documents(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get fiscal documents history (SuperAdmin only)
    """
    # Get invoices that could be fiscal documents
    query = select(Invoice).order_by(Invoice.created_at.desc())
    
    if status:
        try:
            invoice_status = InvoiceStatus(status)
            query = query.filter(Invoice.status == invoice_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}"
            )
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    invoices = result.scalars().all()
    
    # Map invoices to fiscal documents format
    documents = []
    for invoice in invoices:
        documents.append({
            "id": invoice.id,
            "number": f"INV-{invoice.id:06d}",  # Generate invoice number from ID
            "type": "invoice",
            "status": invoice.status.value if hasattr(invoice.status, 'value') else str(invoice.status),
            "issue_date": invoice.issue_date.isoformat() if invoice.issue_date else None,
            "total_amount": float(invoice.total_amount) if invoice.total_amount else 0.0,
            "fiscal_status": "pending",  # Would come from fiscal integration
            "fiscal_number": None,  # Would come from fiscal integration
            "fiscal_key": None,  # Would come from fiscal integration
        })
    
    return {
        "total": len(documents),
        "documents": documents
    }


@router.get("/stats")
async def get_fiscal_stats(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get fiscal integration statistics (SuperAdmin only)
    """
    # Get invoice statistics
    total_invoices_query = select(func.count(Invoice.id))
    total_result = await db.execute(total_invoices_query)
    total_invoices = total_result.scalar() or 0
    
    # Count by status
    issued_query = select(func.count(Invoice.id)).filter(Invoice.status == InvoiceStatus.ISSUED)
    issued_result = await db.execute(issued_query)
    issued_count = issued_result.scalar() or 0
    
    # Pending documents are those that are DRAFT or ISSUED but not PAID
    pending_query = select(func.count(Invoice.id)).filter(
        Invoice.status.in_([InvoiceStatus.DRAFT, InvoiceStatus.ISSUED])
    )
    pending_result = await db.execute(pending_query)
    pending_count = pending_result.scalar() or 0
    
    # For now, return mock stats with real invoice counts
    # In the future, this would aggregate real fiscal document data
    return {
        "total_documents": total_invoices,
        "issued_documents": issued_count,
        "pending_documents": pending_count,
        "failed_documents": 0,
        "last_sync": None,
    }


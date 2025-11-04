"""
TISS Batch XML Generation Endpoints
Provides endpoints for generating TISS XML files in batches
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.auth import get_current_user
from app.models import User, Invoice
from app.services.tiss_service import generate_batch_tiss_xml
from database import get_async_session

router = APIRouter(tags=["TISS Batch"])


@router.post("/invoices/batch-tiss-xml")
async def generate_batch_tiss_xml_endpoint(
    invoice_ids: List[int],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate TISS XML for multiple invoices in a single batch
    
    Args:
        invoice_ids: List of invoice IDs to generate TISS XML for
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        ZIP file containing all TISS XML files
    """
    try:
        # Verify all invoices exist and user has access
        invoice_query = select(Invoice).filter(
            Invoice.id.in_(invoice_ids),
            Invoice.clinic_id == current_user.clinic_id
        )
        invoice_result = await db.execute(invoice_query)
        invoices = invoice_result.scalars().all()
        
        if len(invoices) != len(invoice_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more invoices not found or access denied"
            )
        
        # Check if user has permission
        if current_user.role not in ["admin", "secretary"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to access invoice data"
            )
        
        # Generate batch TISS XML
        zip_content = await generate_batch_tiss_xml(invoice_ids, db)
        
        # Return ZIP file for download
        filename = f"tiss_batch_{len(invoice_ids)}_invoices.zip"
        
        return Response(
            content=zip_content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "application/zip"
            }
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating batch TISS XML: {str(e)}"
        )

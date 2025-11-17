"""
Reports API Endpoints
Handles reports for SuperAdmin
"""

from datetime import date, timedelta, datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_async_session
from app.models import (
    Clinic, User, UserRole, Patient, Appointment,
    Invoice, Payment, InvoiceStatus, PaymentStatus
)
from app.middleware.permissions import require_super_admin
from app.models.license import License, LicenseStatus

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/active-clients")
async def get_active_clients_report(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get active clients report (SuperAdmin only)
    Returns list of active clinics with statistics
    """
    try:
        # Base query for active clinics
        query = select(Clinic).filter(Clinic.is_active == True)
        
        # Apply search filter
        if search:
            search_filter = or_(
                Clinic.name.ilike(f"%{search}%"),
                Clinic.legal_name.ilike(f"%{search}%"),
                Clinic.tax_id.ilike(f"%{search}%"),
                Clinic.email.ilike(f"%{search}%")
            )
            query = query.filter(search_filter)
        
        # Order by name
        query = query.order_by(Clinic.name).offset(skip).limit(limit)
        
        result = await db.execute(query)
        clinics = result.scalars().all()
    except Exception as e:
        # Rollback on error
        await db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching clinics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching clinics: {str(e)}"
        )
    
    # Build response with statistics for each clinic
    clients = []
    for clinic in clinics:
        try:
            # Extract all clinic attributes immediately to avoid async context issues
            # This must be done before any other async operations
            try:
                clinic_id = int(clinic.id) if clinic.id is not None else None
                clinic_name = str(clinic.name) if clinic.name is not None else ""
                clinic_legal_name = str(clinic.legal_name) if clinic.legal_name is not None else ""
                clinic_tax_id = str(clinic.tax_id) if clinic.tax_id is not None else ""
                clinic_email = str(clinic.email) if clinic.email is not None else ""
                clinic_max_users = int(clinic.max_users) if clinic.max_users is not None else 0
                clinic_is_active = bool(clinic.is_active) if clinic.is_active is not None else False
                clinic_license_id = clinic.license_id  # Can be None
                
                # Handle created_at carefully
                clinic_created_at = None
                if hasattr(clinic, 'created_at') and clinic.created_at is not None:
                    created_at_value = clinic.created_at
                    if hasattr(created_at_value, 'isoformat'):
                        clinic_created_at = created_at_value.isoformat()
                    else:
                        clinic_created_at = str(created_at_value)
            except Exception as attr_error:
                # If we can't extract attributes, log and skip this clinic
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error extracting clinic attributes: {str(attr_error)}", exc_info=True)
                continue
            
            # Count active users
            try:
                users_query = select(func.count(User.id)).filter(
                    and_(
                        User.clinic_id == clinic_id,
                        User.is_active == True
                    )
                )
                users_result = await db.execute(users_query)
                user_count = users_result.scalar() or 0
            except Exception as e:
                # If there's an error counting users, rollback and default to 0
                await db.rollback()
                user_count = 0
            
            # Get license information
            license_info = None
            if clinic_license_id:
                try:
                    license_query = select(License).filter(License.id == clinic_license_id)
                    license_result = await db.execute(license_query)
                    license_obj = license_result.scalar_one_or_none()
                    if license_obj:
                        # Extract license attributes immediately to avoid async context issues
                        license_plan = license_obj.plan.value if hasattr(license_obj.plan, 'value') else str(license_obj.plan)
                        license_status = license_obj.status.value if hasattr(license_obj.status, 'value') else str(license_obj.status)
                        license_end_at = None
                        if license_obj.end_at:
                            if hasattr(license_obj.end_at, 'isoformat'):
                                license_end_at = license_obj.end_at.isoformat()
                            else:
                                license_end_at = str(license_obj.end_at)
                        license_info = {
                            "plan": license_plan,
                            "status": license_status,
                            "end_at": license_end_at,
                        }
                except Exception as e:
                    # If there's an error getting license info, rollback and skip it
                    await db.rollback()
                    license_info = None
            
            # Calculate revenue (from paid invoices in the last 30 days)
            try:
                thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
                revenue_query = select(func.coalesce(func.sum(Payment.amount), 0)).join(
                    Invoice, Payment.invoice_id == Invoice.id
                ).filter(
                    and_(
                        Invoice.clinic_id == clinic_id,
                        Payment.status == PaymentStatus.COMPLETED,
                        Payment.created_at >= thirty_days_ago
                    )
                )
                revenue_result = await db.execute(revenue_query)
                revenue_value = revenue_result.scalar()
                revenue = float(revenue_value) if revenue_value is not None else 0.0
            except Exception as e:
                # If there's an error calculating revenue, rollback and default to 0
                await db.rollback()
                revenue = 0.0
            
            # Get last activity (most recent appointment or invoice)
            try:
                last_appointment_query = select(func.max(Appointment.scheduled_datetime)).filter(
                    Appointment.clinic_id == clinic_id
                )
                last_appointment_result = await db.execute(last_appointment_query)
                last_appointment = last_appointment_result.scalar()
                
                last_invoice_query = select(func.max(Invoice.created_at)).filter(
                    Invoice.clinic_id == clinic_id
                )
                last_invoice_result = await db.execute(last_invoice_query)
                last_invoice = last_invoice_result.scalar()
                
                # Determine last activity
                last_activity = None
                if last_appointment and last_invoice:
                    last_activity = max(last_appointment, last_invoice)
                elif last_appointment:
                    last_activity = last_appointment
                elif last_invoice:
                    last_activity = last_invoice
            except Exception as e:
                # If there's an error getting last activity, rollback and set to None
                await db.rollback()
                last_activity = None
        
            # Convert last_activity to string
            last_activity_str = None
            if last_activity:
                if hasattr(last_activity, 'isoformat'):
                    last_activity_str = last_activity.isoformat()
                else:
                    last_activity_str = str(last_activity)
            
            clients.append({
                "id": clinic_id,
                "name": clinic_name,
                "legal_name": clinic_legal_name,
                "tax_id": clinic_tax_id,
                "email": clinic_email,
                "license_type": license_info["plan"] if license_info else "N/A",
                "license_status": license_info["status"] if license_info else "N/A",
                "users": user_count,
                "max_users": clinic_max_users,
                "status": "Ativo" if clinic_is_active else "Inativo",
                "last_activity": last_activity_str,
                "revenue": revenue,
                "created_at": clinic_created_at,
            })
        except Exception as e:
            # If there's an error processing a clinic, rollback, log it and continue with next clinic
            await db.rollback()
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error processing clinic {clinic_id}: {str(e)}", exc_info=True)
            # Continue to next clinic instead of failing the entire request
            continue
    
    return {
        "total": len(clients),
        "clients": clients
    }


@router.get("/active-clients/stats")
async def get_active_clients_stats(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get active clients statistics (SuperAdmin only)
    """
    # Total active clinics
    try:
        total_clinics_query = select(func.count(Clinic.id)).filter(Clinic.is_active == True)
        total_result = await db.execute(total_clinics_query)
        total_clinics_value = total_result.scalar()
        total_clinics = int(total_clinics_value) if total_clinics_value is not None else 0
    except Exception as e:
        total_clinics = 0
    
    # Total active users across all clinics
    try:
        total_users_query = select(func.count(User.id)).filter(
            and_(
                User.is_active == True,
                User.clinic_id.in_(
                    select(Clinic.id).filter(Clinic.is_active == True)
                )
            )
        )
        users_result = await db.execute(total_users_query)
        total_users_value = users_result.scalar()
        total_users = int(total_users_value) if total_users_value is not None else 0
    except Exception as e:
        total_users = 0
    
    # Total revenue (from paid invoices in the last 30 days)
    try:
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        revenue_query = select(func.coalesce(func.sum(Payment.amount), 0)).join(
            Invoice, Payment.invoice_id == Invoice.id
        ).join(
            Clinic, Invoice.clinic_id == Clinic.id
        ).filter(
            and_(
                Clinic.is_active == True,
                Payment.status == PaymentStatus.COMPLETED,
                Payment.created_at >= thirty_days_ago
            )
        )
        revenue_result = await db.execute(revenue_query)
        revenue_value = revenue_result.scalar()
        total_revenue = float(revenue_value) if revenue_value is not None else 0.0
    except Exception as e:
        # If there's an error calculating revenue, default to 0
        total_revenue = 0.0
    
    # Calculate active percentage (all active clinics / all clinics)
    try:
        all_clinics_query = select(func.count(Clinic.id))
        all_clinics_result = await db.execute(all_clinics_query)
        all_clinics_value = all_clinics_result.scalar()
        all_clinics = int(all_clinics_value) if all_clinics_value is not None else 1  # Avoid division by zero
        active_percentage = (float(total_clinics) / float(all_clinics) * 100) if all_clinics > 0 else 0.0
    except Exception as e:
        # If there's an error calculating percentage, default to 0
        all_clinics = 1
        active_percentage = 0.0
    
    # Ensure all values are native Python types
    return {
        "total_clients": int(total_clinics),
        "active_clients": int(total_clinics),  # All are active in this report
        "total_users": int(total_users),
        "total_revenue": float(total_revenue),
        "active_percentage": round(float(active_percentage), 1)
    }


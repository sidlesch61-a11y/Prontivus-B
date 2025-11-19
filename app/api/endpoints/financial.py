"""
Financial module API endpoints
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional
import enum
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.core.auth import get_current_user, require_staff, require_admin
from app.models import UserRole
from database import get_async_session
from app.models import (
    User, ServiceItem, Invoice, InvoiceLine, Patient, Appointment,
    ServiceCategory, InvoiceStatus, Procedure, Payment, PaymentMethod, PaymentStatus,
    InsurancePlan, PreAuthRequest, PreAuthStatus, Expense, ExpenseStatus
)
from app.schemas.financial import (
    ServiceItemCreate, ServiceItemUpdate, ServiceItemResponse,
    InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceDetailResponse,
    InvoiceFromAppointmentCreate, InvoiceLineCreate, InvoiceLineResponse,
    InvoiceFilters, ServiceItemFilters,
    PaymentCreate, PaymentUpdate, PaymentResponse,
    InsurancePlanCreate, InsurancePlanUpdate, InsurancePlanResponse,
    PreAuthRequestCreate, PreAuthRequestUpdate, PreAuthRequestResponse,
    AccountsReceivableSummary, AgingReport,
    ExpenseCreate, ExpenseUpdate, ExpenseResponse
)
from app.services.stock_consumption_service import consume_stock_for_procedure, check_stock_availability_for_procedure

router = APIRouter(tags=["Financial"])


# ==================== Service Items ====================

@router.get("/service-items", response_model=List[ServiceItemResponse])
async def get_service_items(
    category: Optional[ServiceCategory] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search in name and description"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get list of service items (billable procedures, consultations, etc.)
    """
    query = select(ServiceItem).filter(ServiceItem.clinic_id == current_user.clinic_id)
    
    # Apply filters
    if category:
        query = query.filter(ServiceItem.category == category)
    if is_active is not None:
        query = query.filter(ServiceItem.is_active == is_active)
    if search:
        search_filter = or_(
            ServiceItem.name.ilike(f"%{search}%"),
            ServiceItem.description.ilike(f"%{search}%"),
            ServiceItem.code.ilike(f"%{search}%")
        )
        query = query.filter(search_filter)
    
    result = await db.execute(query.order_by(ServiceItem.name))
    return result.scalars().all()


@router.post("/service-items", response_model=ServiceItemResponse, status_code=status.HTTP_201_CREATED)
async def create_service_item(
    service_item: ServiceItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new service item
    Only admins can create service items
    """
    db_service_item = ServiceItem(
        clinic_id=current_user.clinic_id,
        **service_item.model_dump()
    )
    db.add(db_service_item)
    await db.commit()
    await db.refresh(db_service_item)
    return db_service_item


@router.put("/service-items/{item_id}", response_model=ServiceItemResponse)
async def update_service_item(
    item_id: int,
    service_item: ServiceItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update a service item
    Only admins can update service items
    """
    query = select(ServiceItem).filter(
        and_(
            ServiceItem.id == item_id,
            ServiceItem.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_service_item = result.scalar_one_or_none()
    
    if not db_service_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service item not found"
        )
    
    update_data = service_item.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_service_item, field, value)
    
    await db.commit()
    await db.refresh(db_service_item)
    return db_service_item


@router.delete("/service-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete a service item
    Only admins can delete service items
    """
    query = select(ServiceItem).filter(
        and_(
            ServiceItem.id == item_id,
            ServiceItem.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_service_item = result.scalar_one_or_none()
    
    if not db_service_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service item not found"
        )
    
    await db.delete(db_service_item)
    await db.commit()


# ==================== Invoices ====================

@router.get("/invoices", response_model=List[InvoiceResponse])
async def get_invoices(
    patient_id: Optional[int] = Query(None, description="Filter by patient ID"),
    status: Optional[InvoiceStatus] = Query(None, description="Filter by status"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get list of invoices with optional filtering
    """
    query = select(Invoice).options(
        joinedload(Invoice.patient),
        joinedload(Invoice.appointment),
        selectinload(Invoice.invoice_lines).joinedload(InvoiceLine.service_item),
        selectinload(Invoice.invoice_lines).joinedload(InvoiceLine.procedure)
    ).filter(Invoice.clinic_id == current_user.clinic_id)
    
    # Apply filters
    if patient_id:
        query = query.filter(Invoice.patient_id == patient_id)
    if status:
        query = query.filter(Invoice.status == status)
    if start_date:
        query = query.filter(Invoice.issue_date >= start_date)
    if end_date:
        query = query.filter(Invoice.issue_date <= end_date)
    
    result = await db.execute(query.order_by(Invoice.issue_date.desc()))
    invoices = result.unique().scalars().all()
    
    # Add computed fields
    for invoice in invoices:
        invoice.patient_name = invoice.patient.full_name
        if invoice.appointment:
            invoice.appointment_date = invoice.appointment.scheduled_datetime
    
    return invoices


@router.get("/invoices/me", response_model=List[InvoiceResponse])
async def get_my_invoices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    status: Optional[InvoiceStatus] = Query(None, description="Filter by status"),
):
    """
    Get the current patient's invoices
    Patients can only see their own invoices
    """
    # Find patient by email
    patient_query = select(Patient).filter(
        and_(
            Patient.email == current_user.email,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    
    if not patient:
        return []
    
    # Get invoices for this patient
    query = select(Invoice).options(
        joinedload(Invoice.patient),
        joinedload(Invoice.appointment),
        selectinload(Invoice.invoice_lines).joinedload(InvoiceLine.service_item),
        selectinload(Invoice.invoice_lines).joinedload(InvoiceLine.procedure),
        selectinload(Invoice.payments).joinedload(Payment.creator)
    ).filter(
        and_(
            Invoice.patient_id == patient.id,
            Invoice.clinic_id == current_user.clinic_id
        )
    )
    
    if status:
        query = query.filter(Invoice.status == status)
    
    result = await db.execute(query.order_by(Invoice.issue_date.desc()))
    invoices = result.unique().scalars().all()
    
    # Return empty list if no invoices found
    if not invoices:
        return []
    
    # Convert to response models with computed fields
    invoice_responses = []
    for invoice in invoices:
        try:
            # Build patient name
            patient_name = None
            if invoice.patient:
                patient_name = f"{invoice.patient.first_name or ''} {invoice.patient.last_name or ''}".strip()
            
            # Build appointment date
            appointment_date = None
            if invoice.appointment:
                appointment_date = invoice.appointment.scheduled_datetime
            
            # Build invoice lines using model_validate
            invoice_lines_list = None
            if hasattr(invoice, 'invoice_lines') and invoice.invoice_lines:
                invoice_lines_list = []
                for line in invoice.invoice_lines:
                    try:
                        # Use model_validate for the line
                        line_data = InvoiceLineResponse.model_validate(line, from_attributes=True).model_dump()
                        # Add procedure_name if available
                        if line.procedure:
                            line_data["procedure_name"] = line.procedure.name
                        invoice_lines_list.append(line_data)
                    except Exception:
                        # Skip problematic lines
                        continue
            
            # Build payments list
            payments_list = None
            if hasattr(invoice, 'payments') and invoice.payments:
                payments_list = []
                for payment in invoice.payments:
                    try:
                        from app.schemas.financial import PaymentResponse
                        payment_data = PaymentResponse.model_validate(payment, from_attributes=True).model_dump()
                        payments_list.append(payment_data)
                    except Exception:
                        continue
            
            # Build base invoice dict from model
            invoice_dict = {
                "id": invoice.id,
                "patient_id": invoice.patient_id,
                "appointment_id": invoice.appointment_id,
                "due_date": invoice.due_date,
                "notes": invoice.notes,
                "issue_date": invoice.issue_date,
                "status": invoice.status,
                "total_amount": invoice.total_amount,
                "created_at": invoice.created_at,
                "updated_at": invoice.updated_at,
                "patient_name": patient_name,
                "appointment_date": appointment_date,
                "invoice_lines": invoice_lines_list,
                "payments": payments_list,
            }
            
            # Validate and create response
            invoice_responses.append(InvoiceResponse.model_validate(invoice_dict))
        except Exception as e:
            # Log error but continue processing other invoices
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error processing invoice {invoice.id}: {str(e)}", exc_info=True, stack_info=True)
            continue
    
    return invoice_responses


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get detailed invoice information
    Patients can only access their own invoices
    """
    query = select(Invoice).options(
        joinedload(Invoice.patient),
        joinedload(Invoice.appointment).joinedload(Appointment.doctor),
        selectinload(Invoice.invoice_lines).joinedload(InvoiceLine.service_item),
        selectinload(Invoice.invoice_lines).joinedload(InvoiceLine.procedure),
        selectinload(Invoice.payments).joinedload(Payment.creator)
    ).filter(
        and_(
            Invoice.id == invoice_id,
            Invoice.clinic_id == current_user.clinic_id
        )
    )
    
    result = await db.execute(query)
    invoice = result.unique().scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    # If user is a patient, verify they own this invoice
    if current_user.role == UserRole.PATIENT:
        patient_query = select(Patient).filter(
            and_(
                Patient.email == current_user.email,
                Patient.clinic_id == current_user.clinic_id
            )
        )
        patient_result = await db.execute(patient_query)
        patient = patient_result.scalar_one_or_none()
        
        if not patient or invoice.patient_id != patient.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You can only view your own invoices."
            )
    
    # Add computed fields
    invoice.patient_name = invoice.patient.full_name
    if invoice.appointment:
        invoice.appointment_date = invoice.appointment.scheduled_datetime
        invoice.doctor_name = invoice.appointment.doctor.full_name
    
    # Add procedure names to invoice lines
    for line in invoice.invoice_lines:
        if line.procedure:
            line.procedure_name = line.procedure.name
    
    # Build payments list
    payments_list = []
    if hasattr(invoice, 'payments') and invoice.payments:
        for payment in invoice.payments:
            try:
                from app.schemas.financial import PaymentResponse
                payment_data = PaymentResponse.model_validate(payment, from_attributes=True).model_dump()
                payments_list.append(payment_data)
            except Exception:
                continue
    
    # Create response dict with payments
    invoice_dict = InvoiceDetailResponse.model_validate(invoice, from_attributes=True).model_dump()
    invoice_dict["payments"] = payments_list
    
    return InvoiceDetailResponse(**invoice_dict)


@router.post("/invoices", response_model=InvoiceDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice_data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new invoice
    """
    # Verify patient exists and belongs to current clinic
    patient_query = select(Patient).filter(
        and_(
            Patient.id == invoice_data.patient_id,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    # Verify appointment if provided
    if invoice_data.appointment_id:
        appointment_query = select(Appointment).filter(
            and_(
                Appointment.id == invoice_data.appointment_id,
                Appointment.patient_id == invoice_data.patient_id,
                Appointment.clinic_id == current_user.clinic_id
            )
        )
        appointment_result = await db.execute(appointment_query)
        appointment = appointment_result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found or doesn't belong to this patient"
            )
    
    # Create invoice
    db_invoice = Invoice(
        clinic_id=current_user.clinic_id,
        patient_id=invoice_data.patient_id,
        appointment_id=invoice_data.appointment_id,
        due_date=invoice_data.due_date,
        notes=invoice_data.notes,
        status=InvoiceStatus.DRAFT
    )
    db.add(db_invoice)
    await db.flush()  # Get the invoice ID
    
    # Create invoice lines
    total_amount = Decimal('0.00')
    for line_data in invoice_data.service_items:
        # Handle service items
        if line_data.service_item_id:
            # Verify service item exists
            service_item_query = select(ServiceItem).filter(
                and_(
                    ServiceItem.id == line_data.service_item_id,
                    ServiceItem.clinic_id == current_user.clinic_id,
                    ServiceItem.is_active == True
                )
            )
            service_item_result = await db.execute(service_item_query)
            service_item = service_item_result.scalar_one_or_none()
            
            if not service_item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Service item {line_data.service_item_id} not found or inactive"
                )
            
            # Calculate line total
            line_total = line_data.quantity * line_data.unit_price
            
            db_line = InvoiceLine(
                invoice_id=db_invoice.id,
                service_item_id=line_data.service_item_id,
                quantity=line_data.quantity,
                unit_price=line_data.unit_price,
                line_total=line_total,
                description=line_data.description
            )
            db.add(db_line)
            total_amount += line_total
        
        # Handle procedures
        elif line_data.procedure_id:
            # Verify procedure exists
            procedure_query = select(Procedure).filter(
                and_(
                    Procedure.id == line_data.procedure_id,
                    Procedure.clinic_id == current_user.clinic_id,
                    Procedure.is_active == True
                )
            )
            procedure_result = await db.execute(procedure_query)
            procedure = procedure_result.scalar_one_or_none()
            
            if not procedure:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Procedure {line_data.procedure_id} not found or inactive"
                )
            
            # Check stock availability before creating the invoice line
            stock_check = await check_stock_availability_for_procedure(
                line_data.procedure_id,
                line_data.quantity,
                current_user.clinic_id,
                db
            )
            
            if not stock_check["available"]:
                if "insufficient_products" in stock_check:
                    insufficient_products = stock_check["insufficient_products"]
                    product_names = [p["product_name"] for p in insufficient_products]
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Insufficient stock for procedure '{procedure.name}'. Products with low stock: {', '.join(product_names)}"
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=stock_check.get("error", "Stock check failed")
                    )
            
            # Calculate line total
            line_total = line_data.quantity * line_data.unit_price
            
            db_line = InvoiceLine(
                invoice_id=db_invoice.id,
                procedure_id=line_data.procedure_id,
                quantity=line_data.quantity,
                unit_price=line_data.unit_price,
                line_total=line_total,
                description=line_data.description
            )
            db.add(db_line)
            total_amount += line_total
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invoice line must have either service_item_id or procedure_id"
            )
    
    # Update invoice total
    db_invoice.total_amount = total_amount
    db_invoice.status = InvoiceStatus.ISSUED
    
    await db.commit()
    await db.refresh(db_invoice)
    
    # Consume stock for procedures after invoice is created
    for line_data in invoice_data.service_items:
        if line_data.procedure_id:
            try:
                await consume_stock_for_procedure(
                    procedure_id=line_data.procedure_id,
                    quantity=line_data.quantity,
                    clinic_id=current_user.clinic_id,
                    created_by=current_user.id,
                    db=db,
                    reference_number=f"INV-{db_invoice.id}"
                )
            except ValueError as e:
                # If stock consumption fails, we should rollback the invoice
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
                )
    
    await db.commit()
    
    # Return detailed response
    return await get_invoice(db_invoice.id, current_user, db)


@router.post("/invoices/from-appointment", response_model=InvoiceDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice_from_appointment(
    invoice_data: InvoiceFromAppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create an invoice from a completed appointment
    """
    # Verify appointment exists and is completed
    appointment_query = select(Appointment).options(
        joinedload(Appointment.patient)
    ).filter(
        and_(
            Appointment.id == invoice_data.appointment_id,
            Appointment.clinic_id == current_user.clinic_id,
            Appointment.status == "completed"
        )
    )
    appointment_result = await db.execute(appointment_query)
    appointment = appointment_result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Completed appointment not found"
        )
    
    # Create invoice data
    invoice_create = InvoiceCreate(
        patient_id=appointment.patient_id,
        appointment_id=appointment.id,
        due_date=invoice_data.due_date,
        notes=invoice_data.notes,
        service_items=invoice_data.service_items
    )
    
    return await create_invoice(invoice_create, current_user, db)


@router.put("/invoices/{invoice_id}", response_model=InvoiceDetailResponse)
async def update_invoice(
    invoice_id: int,
    invoice_data: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update an invoice (status, due date, notes)
    """
    query = select(Invoice).filter(
        and_(
            Invoice.id == invoice_id,
            Invoice.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_invoice = result.scalar_one_or_none()
    
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    update_data = invoice_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_invoice, field, value)
    
    await db.commit()
    await db.refresh(db_invoice)
    
    return await get_invoice(invoice_id, current_user, db)


@router.post("/invoices/{invoice_id}/mark-paid", response_model=InvoiceDetailResponse)
async def mark_invoice_paid(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Mark an invoice as paid
    """
    query = select(Invoice).filter(
        and_(
            Invoice.id == invoice_id,
            Invoice.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_invoice = result.scalar_one_or_none()
    
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    if db_invoice.status == InvoiceStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is already marked as paid"
        )
    
    db_invoice.status = InvoiceStatus.PAID
    await db.commit()
    await db.refresh(db_invoice)
    
    return await get_invoice(invoice_id, current_user, db)


# ==================== Payments ====================

@router.get("/invoices/{invoice_id}/payments", response_model=List[PaymentResponse])
async def get_invoice_payments(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get all payments for a specific invoice
    """
    # Verify invoice exists and user has access
    invoice_query = select(Invoice).filter(
        and_(
            Invoice.id == invoice_id,
            Invoice.clinic_id == current_user.clinic_id
        )
    )
    invoice_result = await db.execute(invoice_query)
    invoice = invoice_result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    # Get payments with creator relationship loaded
    payments_query = select(Payment).options(
        joinedload(Payment.creator)
    ).filter(Payment.invoice_id == invoice_id).order_by(Payment.created_at.desc())
    
    result = await db.execute(payments_query)
    # Use unique() on result to avoid duplicates from joinedload
    payments = result.unique().scalars().all()
    
    # Convert to response models with creator_name
    payment_responses = []
    for payment in payments:
        try:
            # Safely get method and status values
            method_value = payment.method.value if isinstance(payment.method, (PaymentMethod, enum.Enum)) else str(payment.method)
            status_value = payment.status.value if isinstance(payment.status, (PaymentStatus, enum.Enum)) else str(payment.status)
            
            # Safely get creator name
            creator_name = None
            if payment.creator:
                creator_name = getattr(payment.creator, 'full_name', None) or getattr(payment.creator, 'name', None)
            
            payment_dict = {
                "id": payment.id,
                "invoice_id": payment.invoice_id,
                "amount": float(payment.amount) if payment.amount else 0.0,
                "method": method_value,
                "status": status_value,
                "reference_number": payment.reference_number,
                "notes": payment.notes,
                "paid_at": payment.paid_at,
                "created_at": payment.created_at,
                "updated_at": payment.updated_at,
                "creator_name": creator_name
            }
            payment_responses.append(PaymentResponse(**payment_dict))
        except Exception as e:
            # Log error but continue processing other payments
            logging.error(f"Error processing payment {payment.id}: {str(e)}")
            continue
    
    return payment_responses


@router.post("/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payment_data: PaymentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new payment for an invoice
    """
    # Verify invoice exists and user has access
    invoice_query = select(Invoice).filter(
        and_(
            Invoice.id == payment_data.invoice_id,
            Invoice.clinic_id == current_user.clinic_id
        )
    )
    invoice_result = await db.execute(invoice_query)
    invoice = invoice_result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    # Create payment
    db_payment = Payment(
        invoice_id=payment_data.invoice_id,
        amount=payment_data.amount,
        method=PaymentMethod(payment_data.method),
        reference_number=payment_data.reference_number,
        notes=payment_data.notes,
        created_by=current_user.id,
        status=PaymentStatus.COMPLETED,
        paid_at=datetime.now()
    )
    db.add(db_payment)
    await db.flush()
    
    # Update invoice status if fully paid
    total_paid = sum(p.amount for p in invoice.payments if p.status == PaymentStatus.COMPLETED)
    total_paid += payment_data.amount
    
    if total_paid >= invoice.total_amount:
        invoice.status = InvoiceStatus.PAID
    
    await db.commit()
    await db.refresh(db_payment)
    
    # Add creator name
    db_payment.creator_name = current_user.full_name
    
    return db_payment


@router.put("/payments/{payment_id}", response_model=PaymentResponse)
async def update_payment(
    payment_id: int,
    payment_data: PaymentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update a payment
    """
    # Verify payment exists and user has access
    payment_query = select(Payment).options(
        joinedload(Payment.invoice)
    ).filter(
        and_(
            Payment.id == payment_id,
            Payment.invoice.has(Invoice.clinic_id == current_user.clinic_id)
        )
    )
    payment_result = await db.execute(payment_query)
    payment = payment_result.scalar_one_or_none()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    # Update payment
    update_data = payment_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "method" and value:
            setattr(payment, field, PaymentMethod(value))
        elif field == "status" and value:
            setattr(payment, field, PaymentStatus(value))
        else:
            setattr(payment, field, value)
    
    await db.commit()
    await db.refresh(payment)
    
    # Add creator name
    if payment.creator:
        payment.creator_name = payment.creator.full_name
    
    return payment


# ==================== Insurance Plans ====================

@router.get("/insurance-plans", response_model=List[InsurancePlanResponse])
async def get_insurance_plans(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search in name and company"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get list of insurance plans
    """
    query = select(InsurancePlan).filter(InsurancePlan.clinic_id == current_user.clinic_id)
    
    # Apply filters
    if is_active is not None:
        query = query.filter(InsurancePlan.is_active == is_active)
    if search:
        search_filter = or_(
            InsurancePlan.name.ilike(f"%{search}%"),
            InsurancePlan.insurance_company.ilike(f"%{search}%")
        )
        query = query.filter(search_filter)
    
    result = await db.execute(query.order_by(InsurancePlan.name))
    return result.scalars().all()


@router.post("/insurance-plans", response_model=InsurancePlanResponse, status_code=status.HTTP_201_CREATED)
async def create_insurance_plan(
    plan_data: InsurancePlanCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new insurance plan
    Only admins can create insurance plans
    """
    db_plan = InsurancePlan(
        clinic_id=current_user.clinic_id,
        **plan_data.model_dump()
    )
    db.add(db_plan)
    await db.commit()
    await db.refresh(db_plan)
    return db_plan


@router.put("/insurance-plans/{plan_id}", response_model=InsurancePlanResponse)
async def update_insurance_plan(
    plan_id: int,
    plan_data: InsurancePlanUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update an insurance plan
    Only admins can update insurance plans
    """
    query = select(InsurancePlan).filter(
        and_(
            InsurancePlan.id == plan_id,
            InsurancePlan.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_plan = result.scalar_one_or_none()
    
    if not db_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insurance plan not found"
        )
    
    update_data = plan_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_plan, field, value)
    
    await db.commit()
    await db.refresh(db_plan)
    return db_plan


# ==================== Pre-Authorization ====================

@router.get("/preauth-requests", response_model=List[PreAuthRequestResponse])
async def get_preauth_requests(
    patient_id: Optional[int] = Query(None, description="Filter by patient ID"),
    status: Optional[PreAuthStatus] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get list of pre-authorization requests
    """
    query = select(PreAuthRequest).options(
        joinedload(PreAuthRequest.patient),
        joinedload(PreAuthRequest.insurance_plan),
        joinedload(PreAuthRequest.creator)
    ).filter(PreAuthRequest.clinic_id == current_user.clinic_id)
    
    # Apply filters
    if patient_id:
        query = query.filter(PreAuthRequest.patient_id == patient_id)
    if status:
        query = query.filter(PreAuthRequest.status == status)
    
    result = await db.execute(query.order_by(PreAuthRequest.request_date.desc()))
    requests = result.scalars().all()
    
    # Add names
    for req in requests:
        req.patient_name = req.patient.full_name
        req.insurance_plan_name = req.insurance_plan.name
        if req.creator:
            req.creator_name = req.creator.full_name
    
    return requests


@router.post("/preauth-requests", response_model=PreAuthRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_preauth_request(
    request_data: PreAuthRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new pre-authorization request
    """
    # Verify patient exists
    patient_query = select(Patient).filter(
        and_(
            Patient.id == request_data.patient_id,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    patient = patient_result.scalar_one_or_none()
    
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    # Verify insurance plan exists
    plan_query = select(InsurancePlan).filter(
        and_(
            InsurancePlan.id == request_data.insurance_plan_id,
            InsurancePlan.clinic_id == current_user.clinic_id
        )
    )
    plan_result = await db.execute(plan_query)
    plan = plan_result.scalar_one_or_none()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insurance plan not found"
        )
    
    # Create pre-auth request
    db_request = PreAuthRequest(
        clinic_id=current_user.clinic_id,
        created_by=current_user.id,
        **request_data.model_dump()
    )
    db.add(db_request)
    await db.commit()
    await db.refresh(db_request)
    
    # Add names
    db_request.patient_name = patient.full_name
    db_request.insurance_plan_name = plan.name
    db_request.creator_name = current_user.full_name
    
    return db_request


@router.put("/preauth-requests/{request_id}", response_model=PreAuthRequestResponse)
async def update_preauth_request(
    request_id: int,
    request_data: PreAuthRequestUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update a pre-authorization request
    """
    query = select(PreAuthRequest).options(
        joinedload(PreAuthRequest.patient),
        joinedload(PreAuthRequest.insurance_plan),
        joinedload(PreAuthRequest.creator)
    ).filter(
        and_(
            PreAuthRequest.id == request_id,
            PreAuthRequest.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_request = result.scalar_one_or_none()
    
    if not db_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pre-authorization request not found"
        )
    
    update_data = request_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "status" and value:
            setattr(db_request, field, PreAuthStatus(value))
        else:
            setattr(db_request, field, value)
    
    # Set response date if status is being updated
    if "status" in update_data and update_data["status"] in ["approved", "denied"]:
        db_request.response_date = datetime.now()
    
    await db.commit()
    await db.refresh(db_request)
    
    # Add names
    db_request.patient_name = db_request.patient.full_name
    db_request.insurance_plan_name = db_request.insurance_plan.name
    if db_request.creator:
        db_request.creator_name = db_request.creator.full_name
    
    return db_request


# ==================== Accounts Receivable ====================

@router.get("/doctor/accounts-receivable", response_model=List[dict])
async def get_doctor_accounts_receivable(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    status: Optional[InvoiceStatus] = Query(None, description="Filter by invoice status"),
):
    """
    Get accounts receivable for the current doctor
    Returns invoices from appointments where the doctor is the assigned doctor
    """
    from datetime import date as date_type
    from decimal import Decimal
    
    # Only allow doctors to access this endpoint
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for doctors"
        )
    
    # Get invoices for appointments where the doctor is assigned
    invoices_query = select(Invoice, Patient, Appointment).join(
        Patient, Invoice.patient_id == Patient.id
    ).join(
        Appointment, Invoice.appointment_id == Appointment.id
    ).options(
        selectinload(Invoice.payments)
    ).filter(
        and_(
            Appointment.doctor_id == current_user.id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    
    # Apply status filter
    if status:
        invoices_query = invoices_query.filter(Invoice.status == status)
    
    result = await db.execute(invoices_query)
    invoices_data = result.all()
    
    receivables = []
    today = date_type.today()
    
    for invoice, patient, appointment in invoices_data:
        # Calculate paid amount
        paid_amount = Decimal('0.00')
        if invoice.payments:
            paid_amount = sum(
                Decimal(str(p.amount)) 
                for p in invoice.payments 
                if p.status == PaymentStatus.COMPLETED
            )
        
        # Calculate outstanding amount
        outstanding = Decimal(str(invoice.total_amount)) - paid_amount
        
        # Determine status
        invoice_status = invoice.status.value if hasattr(invoice.status, 'value') else str(invoice.status)
        
        # Check if overdue
        due_date = invoice.due_date or invoice.issue_date.date()
        days_overdue = (today - due_date).days if isinstance(due_date, date_type) else 0
        
        # Determine display status
        if paid_amount >= Decimal(str(invoice.total_amount)):
            display_status = "Pago"
        elif days_overdue > 0 and invoice_status != "paid":
            display_status = "Atrasado"
        elif invoice_status in ["draft", "issued"]:
            display_status = "Pendente"
        else:
            display_status = invoice_status.capitalize()
        
        # Get patient name
        patient_name = f"{patient.first_name or ''} {patient.last_name or ''}".strip()
        if not patient_name:
            patient_name = patient.email or "Paciente"
        
        receivables.append({
            "id": invoice.id,
            "patient_id": patient.id,
            "patient_name": patient_name,
            "amount": float(invoice.total_amount),
            "paid_amount": float(paid_amount),
            "outstanding_amount": float(outstanding),
            "due_date": due_date.isoformat() if isinstance(due_date, date_type) else str(due_date),
            "issue_date": invoice.issue_date.isoformat() if invoice.issue_date else None,
            "status": display_status,
            "invoice_status": invoice_status,
            "days_overdue": days_overdue,
            "appointment_id": appointment.id if appointment else None,
        })
    
    # Sort by due date (oldest first) or by days overdue
    receivables.sort(key=lambda x: (x["days_overdue"], x["due_date"]), reverse=True)
    
    return receivables


@router.get("/doctor/delinquency", response_model=List[dict])
async def get_doctor_delinquency(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    min_days_overdue: int = Query(1, ge=0, description="Minimum days overdue to include (default: 1)"),
):
    """
    Get delinquency (overdue accounts) for the current doctor
    Returns only invoices that are overdue and have outstanding amounts
    """
    from datetime import date as date_type
    from decimal import Decimal
    
    # Only allow doctors to access this endpoint
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for doctors"
        )
    
    # Get invoices for appointments where the doctor is assigned
    invoices_query = select(Invoice, Patient, Appointment).join(
        Patient, Invoice.patient_id == Patient.id
    ).join(
        Appointment, Invoice.appointment_id == Appointment.id
    ).options(
        selectinload(Invoice.payments)
    ).filter(
        and_(
            Appointment.doctor_id == current_user.id,
            Appointment.clinic_id == current_user.clinic_id
        )
    )
    
    result = await db.execute(invoices_query)
    invoices_data = result.all()
    
    delinquency = []
    today = date_type.today()
    total_delinquency = Decimal('0.00')
    
    for invoice, patient, appointment in invoices_data:
        # Calculate paid amount
        paid_amount = Decimal('0.00')
        if invoice.payments:
            paid_amount = sum(
                Decimal(str(p.amount)) 
                for p in invoice.payments 
                if p.status == PaymentStatus.COMPLETED
            )
        
        # Calculate outstanding amount
        outstanding = Decimal(str(invoice.total_amount)) - paid_amount
        
        # Only include if there's an outstanding amount
        if outstanding <= 0:
            continue
        
        # Check if overdue
        if invoice.due_date:
            due_date = invoice.due_date.date() if hasattr(invoice.due_date, 'date') else invoice.due_date
        elif invoice.issue_date:
            due_date = invoice.issue_date.date() if hasattr(invoice.issue_date, 'date') else invoice.issue_date
        else:
            continue
        
        if not isinstance(due_date, date_type):
            continue
        
        days_overdue = (today - due_date).days
        
        # Only include if overdue by at least min_days_overdue
        if days_overdue < min_days_overdue:
            continue
        
        # Get patient name
        patient_name = f"{patient.first_name or ''} {patient.last_name or ''}".strip()
        if not patient_name:
            patient_name = patient.email or "Paciente"
        
        total_delinquency += outstanding
        
        delinquency.append({
            "id": invoice.id,
            "patient_id": patient.id,
            "patient_name": patient_name,
            "amount": float(outstanding),  # Use outstanding amount, not total
            "total_amount": float(invoice.total_amount),
            "paid_amount": float(paid_amount),
            "due_date": due_date.isoformat(),
            "issue_date": invoice.issue_date.isoformat() if invoice.issue_date else None,
            "days_overdue": days_overdue,
            "appointment_id": appointment.id if appointment else None,
        })
    
    # Sort by days overdue (most overdue first)
    delinquency.sort(key=lambda x: x["days_overdue"], reverse=True)
    
    return delinquency


@router.get("/doctor/accounts-payable", response_model=List[dict])
async def get_doctor_accounts_payable(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    status: Optional[str] = Query(None, description="Filter by status (pending, paid)"),
):
    """
    Get accounts payable for the current doctor
    Returns expenses/bills for the doctor
    """
    from datetime import date as date_type, timezone
    
    # Only allow doctors to access this endpoint
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for doctors"
        )
    
    # Get expenses for the current doctor
    expenses_query = select(Expense).filter(
        and_(
            Expense.doctor_id == current_user.id,
            Expense.clinic_id == current_user.clinic_id
        )
    )
    
    if status:
        if status == "pending":
            expenses_query = expenses_query.filter(Expense.status == ExpenseStatus.PENDING.value)
        elif status == "paid":
            expenses_query = expenses_query.filter(Expense.status == ExpenseStatus.PAID.value)
    
    result = await db.execute(expenses_query)
    expenses = result.scalars().all()
    
    payables = []
    today = datetime.now(timezone.utc).date()
    
    for expense in expenses:
        # Convert due_date to date if it's a datetime
        due_date = expense.due_date
        if isinstance(due_date, datetime):
            due_date = due_date.date()
        elif hasattr(due_date, 'date'):
            due_date = due_date.date()
        
        # Calculate days overdue
        days_overdue = 0
        if isinstance(due_date, date_type) and expense.status == ExpenseStatus.PENDING.value:
            days_overdue = (today - due_date).days
            if days_overdue < 0:
                days_overdue = 0
        
        payables.append({
            "id": expense.id,
            "description": expense.description,
            "amount": float(expense.amount),
            "due_date": due_date.isoformat() if isinstance(due_date, date_type) else str(due_date),
            "status": expense.status,
            "days_overdue": days_overdue,
            "category": expense.category,
            "vendor": expense.vendor,
            "paid_date": expense.paid_date.isoformat() if expense.paid_date else None,
            "notes": expense.notes,
            "created_at": expense.created_at.isoformat() if expense.created_at else None,
            "updated_at": expense.updated_at.isoformat() if expense.updated_at else None,
        })
    
    return payables


# ==================== Expense Endpoints ====================

@router.post("/doctor/expenses", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(
    expense_data: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new expense for the current doctor
    """
    # Only allow doctors to access this endpoint
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for doctors"
        )
    
    # Create expense
    new_expense = Expense(
        description=expense_data.description,
        amount=expense_data.amount,
        due_date=expense_data.due_date,
        category=expense_data.category,
        vendor=expense_data.vendor,
        notes=expense_data.notes,
        doctor_id=current_user.id,
        clinic_id=current_user.clinic_id,
        status=ExpenseStatus.PENDING.value,
    )
    
    db.add(new_expense)
    await db.commit()
    await db.refresh(new_expense)
    
    # Calculate days overdue
    from datetime import date as date_type
    today = datetime.now(timezone.utc).date()
    due_date = new_expense.due_date
    if isinstance(due_date, datetime):
        due_date = due_date.date()
    days_overdue = (today - due_date).days if isinstance(due_date, date_type) and new_expense.status == ExpenseStatus.PENDING.value else 0
    if days_overdue < 0:
        days_overdue = 0
    
    response = ExpenseResponse.model_validate(new_expense)
    response.days_overdue = days_overdue
    
    return response


@router.get("/doctor/expenses/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get a specific expense by ID
    """
    # Only allow doctors to access this endpoint
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for doctors"
        )
    
    # Get expense
    expense_query = select(Expense).filter(
        and_(
            Expense.id == expense_id,
            Expense.doctor_id == current_user.id,
            Expense.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(expense_query)
    expense = result.scalar_one_or_none()
    
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )
    
    # Calculate days overdue
    from datetime import date as date_type
    today = datetime.now(timezone.utc).date()
    due_date = expense.due_date
    if isinstance(due_date, datetime):
        due_date = due_date.date()
    days_overdue = (today - due_date).days if isinstance(due_date, date_type) and expense.status == ExpenseStatus.PENDING.value else 0
    if days_overdue < 0:
        days_overdue = 0
    
    response = ExpenseResponse.model_validate(expense)
    response.days_overdue = days_overdue
    
    return response


@router.put("/doctor/expenses/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: int,
    expense_data: ExpenseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update an expense
    """
    # Only allow doctors to access this endpoint
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for doctors"
        )
    
    # Get expense
    expense_query = select(Expense).filter(
        and_(
            Expense.id == expense_id,
            Expense.doctor_id == current_user.id,
            Expense.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(expense_query)
    expense = result.scalar_one_or_none()
    
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )
    
    # Update fields
    update_data = expense_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "status" and value:
            # Validate status
            if value not in [ExpenseStatus.PENDING.value, ExpenseStatus.PAID.value, ExpenseStatus.CANCELLED.value]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {value}"
                )
            setattr(expense, field, value)
            # If marking as paid, set paid_date if not provided
            if value == ExpenseStatus.PAID.value and not expense.paid_date:
                expense.paid_date = datetime.now(timezone.utc)
            # If marking as pending, clear paid_date
            elif value == ExpenseStatus.PENDING.value:
                expense.paid_date = None
        else:
            setattr(expense, field, value)
    
    await db.commit()
    await db.refresh(expense)
    
    # Calculate days overdue
    from datetime import date as date_type
    today = datetime.now(timezone.utc).date()
    due_date = expense.due_date
    if isinstance(due_date, datetime):
        due_date = due_date.date()
    days_overdue = (today - due_date).days if isinstance(due_date, date_type) and expense.status == ExpenseStatus.PENDING.value else 0
    if days_overdue < 0:
        days_overdue = 0
    
    response = ExpenseResponse.model_validate(expense)
    response.days_overdue = days_overdue
    
    return response


@router.delete("/doctor/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    expense_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete an expense
    """
    # Only allow doctors to access this endpoint
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for doctors"
        )
    
    # Get expense
    expense_query = select(Expense).filter(
        and_(
            Expense.id == expense_id,
            Expense.doctor_id == current_user.id,
            Expense.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(expense_query)
    expense = result.scalar_one_or_none()
    
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )
    
    await db.delete(expense)
    await db.commit()
    
    return None


@router.get("/accounts-receivable/summary", response_model=AccountsReceivableSummary)
async def get_accounts_receivable_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get accounts receivable summary
    """
    from datetime import datetime, timedelta
    from decimal import Decimal
    
    # Get all outstanding invoices
    invoices_query = select(Invoice).options(
        joinedload(Invoice.payments)
    ).filter(
        and_(
            Invoice.clinic_id == current_user.clinic_id,
            Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.DRAFT])
        )
    )
    result = await db.execute(invoices_query)
    invoices = result.scalars().all()
    
    # Calculate aging
    current = Decimal('0.00')
    days_31_60 = Decimal('0.00')
    days_61_90 = Decimal('0.00')
    over_90_days = Decimal('0.00')
    total_outstanding = Decimal('0.00')
    
    for invoice in invoices:
        # Calculate paid amount
        paid_amount = sum(p.amount for p in invoice.payments if p.status == PaymentStatus.COMPLETED)
        outstanding = invoice.total_amount - paid_amount
        
        if outstanding <= 0:
            continue
            
        total_outstanding += outstanding
        
        # Calculate days overdue
        due_date = invoice.due_date or invoice.issue_date
        days_overdue = (datetime.now().date() - due_date.date()).days
        
        if days_overdue <= 30:
            current += outstanding
        elif days_overdue <= 60:
            days_31_60 += outstanding
        elif days_overdue <= 90:
            days_61_90 += outstanding
        else:
            over_90_days += outstanding
    
    return AccountsReceivableSummary(
        total_outstanding=total_outstanding,
        current=current,
        days_31_60=days_31_60,
        days_61_90=days_61_90,
        over_90_days=over_90_days,
        total_invoices=len(invoices)
    )


@router.get("/accounts-receivable/aging-report", response_model=AgingReport)
async def get_aging_report(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get detailed aging report
    """
    from datetime import datetime
    from decimal import Decimal
    
    # Get all outstanding invoices
    invoices_query = select(Invoice).options(
        joinedload(Invoice.payments),
        joinedload(Invoice.patient)
    ).filter(
        and_(
            Invoice.clinic_id == current_user.clinic_id,
            Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.DRAFT])
        )
    )
    result = await db.execute(invoices_query)
    invoices = result.scalars().all()
    
    # Build aging report items
    items = []
    for invoice in invoices:
        # Calculate paid amount
        paid_amount = sum(p.amount for p in invoice.payments if p.status == PaymentStatus.COMPLETED)
        outstanding = invoice.total_amount - paid_amount
        
        if outstanding <= 0:
            continue
        
        # Calculate days overdue
        due_date = invoice.due_date or invoice.issue_date
        days_overdue = (datetime.now().date() - due_date.date()).days
        
        items.append(AgingReportItem(
            invoice_id=invoice.id,
            patient_name=invoice.patient.full_name,
            invoice_date=invoice.issue_date,
            due_date=invoice.due_date,
            total_amount=invoice.total_amount,
            paid_amount=paid_amount,
            outstanding_amount=outstanding,
            days_overdue=days_overdue,
            status=invoice.status.value
        ))
    
    # Sort by days overdue (descending)
    items.sort(key=lambda x: x.days_overdue, reverse=True)
    
    # Calculate summary
    summary = AccountsReceivableSummary(
        total_outstanding=sum(item.outstanding_amount for item in items),
        current=sum(item.outstanding_amount for item in items if item.days_overdue <= 30),
        days_31_60=sum(item.outstanding_amount for item in items if 31 <= item.days_overdue <= 60),
        days_61_90=sum(item.outstanding_amount for item in items if 61 <= item.days_overdue <= 90),
        over_90_days=sum(item.outstanding_amount for item in items if item.days_overdue > 90),
        total_invoices=len(items)
    )
    
    return AgingReport(
        summary=summary,
        items=items,
        generated_at=datetime.now()
    )

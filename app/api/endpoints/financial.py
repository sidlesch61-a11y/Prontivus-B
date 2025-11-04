"""
Financial module API endpoints
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.core.auth import get_current_user, require_staff, require_admin
from database import get_async_session
from app.models import (
    User, ServiceItem, Invoice, InvoiceLine, Patient, Appointment,
    ServiceCategory, InvoiceStatus, Procedure, Payment, PaymentMethod, PaymentStatus,
    InsurancePlan, PreAuthRequest, PreAuthStatus
)
from app.schemas.financial import (
    ServiceItemCreate, ServiceItemUpdate, ServiceItemResponse,
    InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceDetailResponse,
    InvoiceFromAppointmentCreate, InvoiceLineCreate, InvoiceLineResponse,
    InvoiceFilters, ServiceItemFilters,
    PaymentCreate, PaymentUpdate, PaymentResponse,
    InsurancePlanCreate, InsurancePlanUpdate, InsurancePlanResponse,
    PreAuthRequestCreate, PreAuthRequestUpdate, PreAuthRequestResponse,
    AccountsReceivableSummary, AgingReport
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


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get detailed invoice information
    """
    query = select(Invoice).options(
        joinedload(Invoice.patient),
        joinedload(Invoice.appointment).joinedload(Appointment.doctor),
        joinedload(Invoice.invoice_lines).joinedload(InvoiceLine.service_item),
        joinedload(Invoice.invoice_lines).joinedload(InvoiceLine.procedure)
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
    
    # Add computed fields
    invoice.patient_name = invoice.patient.full_name
    if invoice.appointment:
        invoice.appointment_date = invoice.appointment.scheduled_datetime
        invoice.doctor_name = invoice.appointment.doctor.full_name
    
    # Add procedure names to invoice lines
    for line in invoice.invoice_lines:
        if line.procedure:
            line.procedure_name = line.procedure.name
    
    return invoice


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
    
    # Get payments
    payments_query = select(Payment).options(
        joinedload(Payment.creator)
    ).filter(Payment.invoice_id == invoice_id).order_by(Payment.created_at.desc())
    
    result = await db.execute(payments_query)
    payments = result.scalars().all()
    
    # Add creator names
    for payment in payments:
        if payment.creator:
            payment.creator_name = payment.creator.full_name
    
    return payments


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

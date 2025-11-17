"""
Support Ticket and Help Article API Endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
import json

from database import get_async_session
from app.core.auth import get_current_user, require_staff
from app.models import User, UserRole, Patient
from app.models.support import SupportTicket, HelpArticle, TicketStatus, TicketPriority
from app.schemas.support import (
    SupportTicketCreate,
    SupportTicketUpdate,
    SupportTicketResponse,
    HelpArticleCreate,
    HelpArticleUpdate,
    HelpArticleResponse,
)

router = APIRouter(prefix="/support", tags=["Support"])


async def get_patient_from_user(current_user: User, db: AsyncSession) -> Optional[Patient]:
    """Helper to get patient record from user"""
    from sqlalchemy import select, and_
    patient_query = select(Patient).filter(
        and_(
            Patient.email == current_user.email,
            Patient.clinic_id == current_user.clinic_id
        )
    )
    patient_result = await db.execute(patient_query)
    return patient_result.scalar_one_or_none()


# ==================== Support Tickets ====================

@router.get("/tickets", response_model=List[SupportTicketResponse])
async def get_my_tickets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    status_filter: Optional[TicketStatus] = Query(None, alias="status"),
):
    """
    Get current patient's support tickets
    """
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for patients"
        )
    
    patient = await get_patient_from_user(current_user, db)
    if not patient:
        return []
    
    query = select(SupportTicket).filter(
        and_(
            SupportTicket.patient_id == patient.id,
            SupportTicket.clinic_id == current_user.clinic_id,
            SupportTicket.is_active == True
        )
    )
    
    if status_filter:
        query = query.filter(SupportTicket.status == status_filter)
    
    query = query.order_by(SupportTicket.created_at.desc())
    
    result = await db.execute(query)
    tickets = result.scalars().all()
    
    return [SupportTicketResponse.model_validate(ticket) for ticket in tickets]


@router.post("/tickets", response_model=SupportTicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    ticket_data: SupportTicketCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new support ticket
    """
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for patients"
        )
    
    patient = await get_patient_from_user(current_user, db)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found"
        )
    
    ticket = SupportTicket(
        patient_id=patient.id,
        clinic_id=current_user.clinic_id,
        subject=ticket_data.subject,
        description=ticket_data.description,
        priority=ticket_data.priority,
        status=TicketStatus.OPEN
    )
    
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    
    return SupportTicketResponse.model_validate(ticket)


@router.get("/tickets/{ticket_id}", response_model=SupportTicketResponse)
async def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get a specific support ticket
    """
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for patients"
        )
    
    patient = await get_patient_from_user(current_user, db)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found"
        )
    
    query = select(SupportTicket).filter(
        and_(
            SupportTicket.id == ticket_id,
            SupportTicket.patient_id == patient.id,
            SupportTicket.clinic_id == current_user.clinic_id
        )
    )
    
    result = await db.execute(query)
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )
    
    return SupportTicketResponse.model_validate(ticket)


@router.put("/tickets/{ticket_id}", response_model=SupportTicketResponse)
async def update_ticket(
    ticket_id: int,
    ticket_data: SupportTicketUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update a support ticket (patients can only update their own tickets)
    """
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for patients"
        )
    
    patient = await get_patient_from_user(current_user, db)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found"
        )
    
    query = select(SupportTicket).filter(
        and_(
            SupportTicket.id == ticket_id,
            SupportTicket.patient_id == patient.id,
            SupportTicket.clinic_id == current_user.clinic_id
        )
    )
    
    result = await db.execute(query)
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )
    
    # Patients can only update subject, description, and priority
    # Status updates are handled by staff
    update_data = ticket_data.model_dump(exclude_unset=True)
    if "status" in update_data:
        del update_data["status"]  # Patients cannot change status
    
    for field, value in update_data.items():
        setattr(ticket, field, value)
    
    await db.commit()
    await db.refresh(ticket)
    
    return SupportTicketResponse.model_validate(ticket)


# ==================== Help Articles ====================

@router.get("/articles", response_model=List[HelpArticleResponse])
async def get_help_articles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """
    Get help articles (available to all authenticated users)
    Returns clinic-specific articles and global articles (clinic_id is None)
    """
    query = select(HelpArticle).filter(
        and_(
            HelpArticle.is_active == True,
            or_(
                HelpArticle.clinic_id == current_user.clinic_id,
                HelpArticle.clinic_id.is_(None)  # Global articles
            )
        )
    )
    
    if category:
        query = query.filter(HelpArticle.category == category)
    
    if search:
        search_filter = or_(
            HelpArticle.title.ilike(f"%{search}%"),
            HelpArticle.content.ilike(f"%{search}%"),
            HelpArticle.tags.ilike(f"%{search}%")
        )
        query = query.filter(search_filter)
    
    query = query.order_by(HelpArticle.created_at.desc())
    
    result = await db.execute(query)
    articles = result.scalars().all()
    
    # Parse tags from JSON string
    article_responses = []
    for article in articles:
        article_dict = HelpArticleResponse.model_validate(article).model_dump()
        # Parse tags from JSON string if exists
        if article.tags:
            try:
                article_dict["tags"] = json.loads(article.tags) if isinstance(article.tags, str) else article.tags
            except:
                article_dict["tags"] = []
        else:
            article_dict["tags"] = []
        article_responses.append(HelpArticleResponse(**article_dict))
    
    return article_responses


@router.get("/articles/categories", response_model=List[str])
async def get_article_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get list of unique article categories
    Must be defined before /articles/{article_id} to ensure correct route matching
    """
    query = select(HelpArticle.category).filter(
        and_(
            HelpArticle.is_active == True,
            or_(
                HelpArticle.clinic_id == current_user.clinic_id,
                HelpArticle.clinic_id.is_(None)
            )
        )
    ).distinct()
    
    result = await db.execute(query)
    categories = [row[0] for row in result.all()]
    
    return sorted(categories)


@router.get("/articles/{article_id}", response_model=HelpArticleResponse)
async def get_help_article(
    article_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get a specific help article and increment view count
    """
    query = select(HelpArticle).filter(
        and_(
            HelpArticle.id == article_id,
            HelpArticle.is_active == True,
            or_(
                HelpArticle.clinic_id == current_user.clinic_id,
                HelpArticle.clinic_id.is_(None)
            )
        )
    )
    
    result = await db.execute(query)
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )
    
    # Increment view count
    article.views = (article.views or 0) + 1
    await db.commit()
    await db.refresh(article)
    
    # Parse tags
    article_dict = HelpArticleResponse.model_validate(article).model_dump()
    if article.tags:
        try:
            article_dict["tags"] = json.loads(article.tags) if isinstance(article.tags, str) else article.tags
        except:
            article_dict["tags"] = []
    else:
        article_dict["tags"] = []
    
    return HelpArticleResponse(**article_dict)


@router.post("/articles/{article_id}/helpful", response_model=HelpArticleResponse)
async def mark_article_helpful(
    article_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Mark a help article as helpful (increment helpful count)
    """
    query = select(HelpArticle).filter(
        and_(
            HelpArticle.id == article_id,
            HelpArticle.is_active == True,
            or_(
                HelpArticle.clinic_id == current_user.clinic_id,
                HelpArticle.clinic_id.is_(None)
            )
        )
    )
    
    result = await db.execute(query)
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )
    
    # Increment helpful count
    article.helpful_count = (article.helpful_count or 0) + 1
    await db.commit()
    await db.refresh(article)
    
    # Parse tags
    article_dict = HelpArticleResponse.model_validate(article).model_dump()
    if article.tags:
        try:
            article_dict["tags"] = json.loads(article.tags) if isinstance(article.tags, str) else article.tags
        except:
            article_dict["tags"] = []
    else:
        article_dict["tags"] = []
    
    return HelpArticleResponse(**article_dict)


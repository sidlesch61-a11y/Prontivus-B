"""
TISS Template API endpoints
Provides CRUD operations for TISS XML templates
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from app.core.auth import get_current_user
from app.middleware.permissions import require_super_admin
from app.models import User, TissTemplate, TissTemplateCategory
from app.schemas.tiss_template import (
    TissTemplateCreate,
    TissTemplateUpdate,
    TissTemplateResponse
)
from database import get_async_session
import re

router = APIRouter(tags=["TISS Templates"])


def extract_variables(xml_template: str) -> List[str]:
    """Extract variable names from XML template (e.g., {{VARIABLE_NAME}})"""
    pattern = r'\{\{(\w+)\}\}'
    variables = re.findall(pattern, xml_template)
    return list(set(variables))  # Return unique variables


@router.get("/templates", response_model=List[TissTemplateResponse])
async def get_tiss_templates(
    category: Optional[TissTemplateCategory] = Query(None, description="Filter by category"),
    is_default: Optional[bool] = Query(None, description="Filter by default status"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search in name and description"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get list of TISS templates
    """
    query = select(TissTemplate).filter(
        TissTemplate.clinic_id == current_user.clinic_id
    )
    
    # Apply filters
    if category:
        query = query.filter(TissTemplate.category == category)
    if is_default is not None:
        query = query.filter(TissTemplate.is_default == is_default)
    if is_active is not None:
        query = query.filter(TissTemplate.is_active == is_active)
    if search:
        search_filter = or_(
            TissTemplate.name.ilike(f"%{search}%"),
            TissTemplate.description.ilike(f"%{search}%")
        )
        query = query.filter(search_filter)
    
    result = await db.execute(query.order_by(TissTemplate.name))
    templates = result.scalars().all()
    
    # Extract variables for each template
    for template in templates:
        if not template.variables:
            template.variables = extract_variables(template.xml_template)
    
    return templates


@router.get("/templates/{template_id}", response_model=TissTemplateResponse)
async def get_tiss_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get a specific TISS template by ID
    """
    query = select(TissTemplate).filter(
        and_(
            TissTemplate.id == template_id,
            TissTemplate.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TISS template not found"
        )
    
    # Extract variables if not already set
    if not template.variables:
        template.variables = extract_variables(template.xml_template)
    
    return template


@router.post("/templates", response_model=TissTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_tiss_template(
    template: TissTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new TISS template
    Only admins can create templates
    """
    try:
        if not current_user.clinic_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not associated with a clinic"
            )
        
        # Extract variables from template
        variables = extract_variables(template.xml_template)
        
        # Get category and ensure it's the enum value (string), not the enum name
        category = template.category
        if isinstance(category, str):
            # Normalize to lowercase and convert to enum
            category_enum = TissTemplateCategory(category.lower())
            category_value = category_enum.value  # Get the string value ("consultation", not "CONSULTATION")
        elif isinstance(category, TissTemplateCategory):
            # Already an enum, get its value
            category_value = category.value
        else:
            # Default to custom
            category_value = TissTemplateCategory.CUSTOM.value
        
        # Create template with category as string value (not enum object)
        # SQLAlchemy with native_enum=False will store it as string
        db_template = TissTemplate(
            clinic_id=current_user.clinic_id,
            created_by_id=current_user.id,
            name=template.name,
            description=template.description,
            category=category_value,  # Use string value, not enum object
            xml_template=template.xml_template,
            variables=variables,
            is_default=template.is_default,
            is_active=template.is_active,
        )
        db.add(db_template)
        await db.commit()
        await db.refresh(db_template)
        
        # Extract variables for response
        if not db_template.variables:
            db_template.variables = extract_variables(db_template.xml_template)
        
        return db_template
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        await db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating TISS template: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating TISS template: {str(e)}"
        )


@router.put("/templates/{template_id}", response_model=TissTemplateResponse)
async def update_tiss_template(
    template_id: int,
    template_update: TissTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update a TISS template
    Only admins can update templates
    """
    query = select(TissTemplate).filter(
        and_(
            TissTemplate.id == template_id,
            TissTemplate.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_template = result.scalar_one_or_none()
    
    if not db_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TISS template not found"
        )
    
    update_data = template_update.model_dump(exclude_unset=True)
    
    # If xml_template is updated, extract new variables
    if 'xml_template' in update_data:
        update_data['variables'] = extract_variables(update_data['xml_template'])
    
    for field, value in update_data.items():
        setattr(db_template, field, value)
    
    await db.commit()
    await db.refresh(db_template)
    return db_template


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tiss_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete a TISS template
    Only admins can delete templates. Default templates cannot be deleted.
    """
    query = select(TissTemplate).filter(
        and_(
            TissTemplate.id == template_id,
            TissTemplate.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_template = result.scalar_one_or_none()
    
    if not db_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TISS template not found"
        )
    
    if db_template.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete default templates"
        )
    
    await db.delete(db_template)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# SuperAdmin endpoints for managing templates for any clinic
@router.post("/admin/{clinic_id}/templates", response_model=TissTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_tiss_template_for_clinic(
    clinic_id: int,
    template: TissTemplateCreate,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new TISS template for a specific clinic (SuperAdmin only)
    """
    try:
        # Validate clinic exists
        from app.models import Clinic
        clinic_result = await db.execute(select(Clinic).where(Clinic.id == clinic_id))
        clinic = clinic_result.scalar_one_or_none()
        if not clinic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Clinic with id {clinic_id} not found"
            )
        
        # Extract variables from template
        variables = extract_variables(template.xml_template)
        
        # Get category and ensure it's the enum value (string), not the enum name
        category = template.category
        if isinstance(category, str):
            # Normalize to lowercase and convert to enum
            category_enum = TissTemplateCategory(category.lower())
            category_value = category_enum.value  # Get the string value ("consultation", not "CONSULTATION")
        elif isinstance(category, TissTemplateCategory):
            # Already an enum, get its value
            category_value = category.value
        else:
            # Default to custom
            category_value = TissTemplateCategory.CUSTOM.value
        
        # Create template with category as string value (not enum object)
        # SQLAlchemy with native_enum=False will store it as string
        db_template = TissTemplate(
            clinic_id=clinic_id,
            created_by_id=current_user.id,
            name=template.name,
            description=template.description,
            category=category_value,  # Use string value, not enum object
            xml_template=template.xml_template,
            variables=variables,
            is_default=template.is_default,
            is_active=template.is_active,
        )
        db.add(db_template)
        await db.commit()
        await db.refresh(db_template)
        
        # Extract variables for response
        if not db_template.variables:
            db_template.variables = extract_variables(db_template.xml_template)
        
        return db_template
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        await db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating TISS template for clinic {clinic_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating TISS template: {str(e)}"
        )


@router.get("/admin/{clinic_id}/templates", response_model=List[TissTemplateResponse])
async def get_tiss_templates_for_clinic(
    clinic_id: int,
    category: Optional[TissTemplateCategory] = Query(None, description="Filter by category"),
    is_default: Optional[bool] = Query(None, description="Filter by default status"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search in name and description"),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get list of TISS templates for a specific clinic (SuperAdmin only)
    """
    query = select(TissTemplate).filter(
        TissTemplate.clinic_id == clinic_id
    )
    
    # Apply filters
    if category:
        query = query.filter(TissTemplate.category == category)
    if is_default is not None:
        query = query.filter(TissTemplate.is_default == is_default)
    if is_active is not None:
        query = query.filter(TissTemplate.is_active == is_active)
    if search:
        search_filter = or_(
            TissTemplate.name.ilike(f"%{search}%"),
            TissTemplate.description.ilike(f"%{search}%")
        )
        query = query.filter(search_filter)
    
    result = await db.execute(query.order_by(TissTemplate.name))
    templates = result.scalars().all()
    
    # Extract variables for each template
    for template in templates:
        if not template.variables:
            template.variables = extract_variables(template.xml_template)
    
    return templates


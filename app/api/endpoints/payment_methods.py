"""
Payment Method Configuration API endpoints
Manages payment method configurations per clinic
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from app.core.auth import get_current_user, RoleChecker
from app.models import User, UserRole, PaymentMethod
from app.models.payment_method_config import PaymentMethodConfig
from database import get_async_session
from pydantic import BaseModel, model_validator

router = APIRouter(prefix="/payment-methods", tags=["Payment Methods"])

# Role checker for admin
require_admin = RoleChecker([UserRole.ADMIN])


def to_datetime_string(dt) -> Optional[str]:
    """Convert datetime to ISO format string"""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, str):
        return dt
    return str(dt)


class PaymentMethodConfigResponse(BaseModel):
    id: int
    clinic_id: int
    method: str
    name: str
    is_active: bool
    is_default: bool
    display_order: int
    created_at: str
    updated_at: Optional[str] = None
    
    @model_validator(mode='before')
    @classmethod
    def convert_datetimes(cls, data):
        """Convert datetime objects to strings before validation"""
        if isinstance(data, dict):
            if 'created_at' in data and isinstance(data['created_at'], datetime):
                data['created_at'] = data['created_at'].isoformat()
            if 'updated_at' in data and isinstance(data['updated_at'], datetime):
                data['updated_at'] = data['updated_at'].isoformat()
        return data
    
    class Config:
        from_attributes = True


class PaymentMethodConfigCreate(BaseModel):
    method: str
    name: str
    is_active: bool = True
    is_default: bool = False
    display_order: int = 0


class PaymentMethodConfigUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    display_order: Optional[int] = None


# Default payment method names in Portuguese
DEFAULT_PAYMENT_METHOD_NAMES = {
    "cash": "Dinheiro",
    "credit_card": "Cartão de Crédito",
    "debit_card": "Cartão de Débito",
    "bank_transfer": "Transferência Bancária",
    "pix": "PIX",
    "check": "Boleto",
    "insurance": "Convênio",
    "other": "Outro",
}


@router.get("", response_model=List[PaymentMethodConfigResponse])
async def get_payment_methods(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get all payment method configurations for the current clinic
    If no configurations exist, returns default configurations
    """
    query = select(PaymentMethodConfig).filter(
        PaymentMethodConfig.clinic_id == current_user.clinic_id
    ).order_by(PaymentMethodConfig.display_order, PaymentMethodConfig.name)
    
    result = await db.execute(query)
    configs = result.scalars().all()
    
    # If no configs exist, return default configs for all payment methods
    if not configs:
        default_configs = []
        for idx, method in enumerate(PaymentMethod):
            default_configs.append(PaymentMethodConfigResponse(
                id=0,  # Temporary ID
                clinic_id=current_user.clinic_id,
                method=method.value,
                name=DEFAULT_PAYMENT_METHOD_NAMES.get(method.value, method.value),
                is_active=True,
                is_default=(method == PaymentMethod.CREDIT_CARD),  # Default to credit card
                display_order=idx,
                created_at="",
                updated_at=None
            ))
        return default_configs
    
    # Convert datetime fields to strings before validation
    response_list = []
    for config in configs:
        config_dict = {
            'id': config.id,
            'clinic_id': config.clinic_id,
            'method': config.method,
            'name': config.name,
            'is_active': config.is_active,
            'is_default': config.is_default,
            'display_order': config.display_order,
            'created_at': to_datetime_string(config.created_at) or "",
            'updated_at': to_datetime_string(config.updated_at),
        }
        response_list.append(PaymentMethodConfigResponse.model_validate(config_dict))
    
    return response_list


@router.post("", response_model=PaymentMethodConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_method(
    config_data: PaymentMethodConfigCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new payment method configuration
    Only admins can create payment methods
    """
    # Validate payment method
    try:
        PaymentMethod(config_data.method)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payment method: {config_data.method}"
        )
    
    # Check if configuration already exists
    existing_query = select(PaymentMethodConfig).filter(
        and_(
            PaymentMethodConfig.clinic_id == current_user.clinic_id,
            PaymentMethodConfig.method == config_data.method
        )
    )
    existing_result = await db.execute(existing_query)
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment method configuration already exists"
        )
    
    # If setting as default, unset other defaults
    if config_data.is_default:
        update_query = select(PaymentMethodConfig).filter(
            and_(
                PaymentMethodConfig.clinic_id == current_user.clinic_id,
                PaymentMethodConfig.is_default == True
            )
        )
        update_result = await db.execute(update_query)
        existing_defaults = update_result.scalars().all()
        for default_config in existing_defaults:
            default_config.is_default = False
    
    # Create new configuration
    db_config = PaymentMethodConfig(
        clinic_id=current_user.clinic_id,
        method=config_data.method,
        name=config_data.name,
        is_active=config_data.is_active,
        is_default=config_data.is_default,
        display_order=config_data.display_order,
    )
    db.add(db_config)
    await db.commit()
    await db.refresh(db_config)
    
    # Convert datetime fields to strings before validation
    config_dict = {
        'id': db_config.id,
        'clinic_id': db_config.clinic_id,
        'method': db_config.method,
        'name': db_config.name,
        'is_active': db_config.is_active,
        'is_default': db_config.is_default,
        'display_order': db_config.display_order,
        'created_at': to_datetime_string(db_config.created_at) or "",
        'updated_at': to_datetime_string(db_config.updated_at),
    }
    return PaymentMethodConfigResponse.model_validate(config_dict)


@router.put("/{config_id}", response_model=PaymentMethodConfigResponse)
async def update_payment_method(
    config_id: int,
    config_data: PaymentMethodConfigUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update a payment method configuration
    Only admins can update payment methods
    """
    query = select(PaymentMethodConfig).filter(
        and_(
            PaymentMethodConfig.id == config_id,
            PaymentMethodConfig.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_config = result.scalar_one_or_none()
    
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method configuration not found"
        )
    
    # If setting as default, unset other defaults
    if config_data.is_default is True:
        update_query = select(PaymentMethodConfig).filter(
            and_(
                PaymentMethodConfig.clinic_id == current_user.clinic_id,
                PaymentMethodConfig.is_default == True,
                PaymentMethodConfig.id != config_id
            )
        )
        update_result = await db.execute(update_query)
        existing_defaults = update_result.scalars().all()
        for default_config in existing_defaults:
            default_config.is_default = False
    
    # Update configuration
    update_data = config_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_config, field, value)
    
    await db.commit()
    await db.refresh(db_config)
    
    # Convert datetime fields to strings before validation
    config_dict = {
        'id': db_config.id,
        'clinic_id': db_config.clinic_id,
        'method': db_config.method,
        'name': db_config.name,
        'is_active': db_config.is_active,
        'is_default': db_config.is_default,
        'display_order': db_config.display_order,
        'created_at': to_datetime_string(db_config.created_at) or "",
        'updated_at': to_datetime_string(db_config.updated_at),
    }
    return PaymentMethodConfigResponse.model_validate(config_dict)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment_method(
    config_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete a payment method configuration
    Only admins can delete payment methods
    """
    query = select(PaymentMethodConfig).filter(
        and_(
            PaymentMethodConfig.id == config_id,
            PaymentMethodConfig.clinic_id == current_user.clinic_id
        )
    )
    result = await db.execute(query)
    db_config = result.scalar_one_or_none()
    
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method configuration not found"
        )
    
    await db.delete(db_config)
    await db.commit()
    
    return None


@router.post("/initialize", response_model=List[PaymentMethodConfigResponse])
async def initialize_payment_methods(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Initialize default payment method configurations for the clinic
    Creates configurations for all payment methods if they don't exist
    """
    # Check existing configs
    existing_query = select(PaymentMethodConfig).filter(
        PaymentMethodConfig.clinic_id == current_user.clinic_id
    )
    existing_result = await db.execute(existing_query)
    existing_configs = existing_result.scalars().all()
    existing_methods = {config.method for config in existing_configs}
    
    # Create missing configurations
    new_configs = []
    for idx, method in enumerate(PaymentMethod):
        if method.value not in existing_methods:
            config = PaymentMethodConfig(
                clinic_id=current_user.clinic_id,
                method=method.value,
                name=DEFAULT_PAYMENT_METHOD_NAMES.get(method.value, method.value),
                is_active=True,
                is_default=(method == PaymentMethod.CREDIT_CARD),
                display_order=idx,
            )
            db.add(config)
            new_configs.append(config)
    
    if new_configs:
        await db.commit()
        for config in new_configs:
            await db.refresh(config)
    
    # Return all configs
    all_query = select(PaymentMethodConfig).filter(
        PaymentMethodConfig.clinic_id == current_user.clinic_id
    ).order_by(PaymentMethodConfig.display_order, PaymentMethodConfig.name)
    
    all_result = await db.execute(all_query)
    all_configs = all_result.scalars().all()
    
    # Convert datetime fields to strings before validation
    response_list = []
    for config in all_configs:
        config_dict = {
            'id': config.id,
            'clinic_id': config.clinic_id,
            'method': config.method,
            'name': config.name,
            'is_active': config.is_active,
            'is_default': config.is_default,
            'display_order': config.display_order,
            'created_at': to_datetime_string(config.created_at) or "",
            'updated_at': to_datetime_string(config.updated_at),
        }
        response_list.append(PaymentMethodConfigResponse.model_validate(config_dict))
    
    return response_list


"""
User management API endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.auth import get_current_user, RoleChecker
from app.models import User, UserRole
from database import get_async_session
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["Users"])

# Role checker for staff
require_staff = RoleChecker([UserRole.ADMIN, UserRole.SECRETARY, UserRole.DOCTOR])


class UserListResponse(BaseModel):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    role: UserRole
    clinic_name: Optional[str] = None
    
    class Config:
        from_attributes = True


@router.get("", response_model=List[UserListResponse])
async def list_users(
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
    role: Optional[UserRole] = Query(None),
):
    """
    List users in the current clinic, optionally filtered by role
    """
    from app.models import Clinic
    query = select(User, Clinic.name).join(Clinic, User.clinic_id == Clinic.id).filter(
        User.clinic_id == current_user.clinic_id,
        User.is_active == True
    )
    
    if role:
        query = query.filter(User.role == role)
    
    query = query.order_by(User.first_name, User.last_name)
    
    result = await db.execute(query)
    users_data = result.all()
    
    users_list = []
    for user, clinic_name in users_data:
        user_dict = UserListResponse.model_validate(user).model_dump()
        user_dict["clinic_name"] = clinic_name
        users_list.append(user_dict)
    
    return users_list


@router.get("/doctors", response_model=List[UserListResponse])
async def get_doctors(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get list of doctors for patients to book appointments
    This endpoint is accessible to all authenticated users
    """
    from app.models import Clinic
    query = select(User, Clinic.name).join(Clinic, User.clinic_id == Clinic.id).filter(
        User.clinic_id == current_user.clinic_id,
        User.role == UserRole.DOCTOR,
        User.is_active == True
    ).order_by(User.first_name, User.last_name)
    
    result = await db.execute(query)
    doctors_data = result.all()
    
    doctors_list = []
    for doctor, clinic_name in doctors_data:
        doctor_dict = UserListResponse.model_validate(doctor).model_dump()
        doctor_dict["clinic_name"] = clinic_name
        doctors_list.append(doctor_dict)
    
    return doctors_list

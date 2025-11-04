"""
User management API endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.auth import get_current_user, RoleChecker
from app.models import User, UserRole
from database import get_async_session
from pydantic import BaseModel
from app.core.security import hash_password

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


class UserCreateRequest(BaseModel):
    username: str
    email: str
    password: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    role: UserRole


class UserUpdateRequest(BaseModel):
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None


@router.post("", response_model=UserListResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    current_user: User = Depends(RoleChecker([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_async_session),
):
    # Ensure unique username/email in clinic scope
    exists = await db.execute(select(User).where(User.username == payload.username))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")
    exists = await db.execute(select(User).where(User.email == payload.email))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists")

    new_user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        first_name=payload.first_name or "",
        last_name=payload.last_name or "",
        role=payload.role,
        clinic_id=current_user.clinic_id,
        is_active=True,
        is_verified=False,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return UserListResponse.model_validate(new_user)


@router.patch("/{user_id}", response_model=UserListResponse)
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    current_user: User = Depends(RoleChecker([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_async_session),
):
    query = select(User).where(and_(User.id == user_id, User.clinic_id == current_user.clinic_id))
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.email is not None:
        user.email = payload.email
    if payload.first_name is not None:
        user.first_name = payload.first_name
    if payload.last_name is not None:
        user.last_name = payload.last_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_verified is not None:
        user.is_verified = payload.is_verified

    await db.commit()
    await db.refresh(user)
    return UserListResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: User = Depends(RoleChecker([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_async_session),
):
    query = select(User).where(and_(User.id == user_id, User.clinic_id == current_user.clinic_id))
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    await db.commit()
    return {"status": "ok"}

"""
User management API endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.auth import get_current_user, RoleChecker
from app.models import User, UserRole
from app.models.menu import UserRole as UserRoleModel
from database import get_async_session
from pydantic import BaseModel
from app.core.security import hash_password

router = APIRouter(prefix="/users", tags=["Users"])

# Role checker for staff
require_staff = RoleChecker([UserRole.ADMIN, UserRole.SECRETARY, UserRole.DOCTOR])


async def is_super_admin(user: User, db: AsyncSession) -> bool:
    """Check if user is SuperAdmin by role_id or role_name"""
    # First check by role_id (most efficient)
    if user.role_id == 1:  # SuperAdmin role_id is 1
        return True
    
    # If role_id is not 1, check by querying the role name
    # This avoids accessing lazy-loaded relationships
    if user.role_id:
        from app.models.menu import UserRole as UserRoleModel
        role_query = await db.execute(
            select(UserRoleModel).where(UserRoleModel.id == user.role_id)
        )
        role = role_query.scalar_one_or_none()
        if role and role.name == "SuperAdmin":
            return True
    
    return False


class UserListResponse(BaseModel):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    role: UserRole
    clinic_id: Optional[int] = None
    clinic_name: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False
    
    class Config:
        from_attributes = True


@router.get("/doctors", response_model=List[UserListResponse])
async def get_doctors(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get list of doctors for patients to book appointments
    This endpoint is accessible to all authenticated users
    Must be defined before the generic "" route to ensure correct matching
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


@router.get("", response_model=List[UserListResponse])
async def list_users(
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_async_session),
    role: Optional[UserRole] = Query(None),
    clinic_id: Optional[int] = Query(None),
):
    """
    List users in the current clinic (or all clinics for SuperAdmin), optionally filtered by role
    Requires staff role (admin, secretary, or doctor)
    SuperAdmin can see all users from all clinics
    """
    from app.models import Clinic
    
    # Check if SuperAdmin
    is_super = await is_super_admin(current_user, db)
    
    # Build query - SuperAdmin can see all users, others only their clinic
    if is_super:
        query = select(User, Clinic.name).join(Clinic, User.clinic_id == Clinic.id)
        # SuperAdmin can filter by clinic_id if provided
        if clinic_id:
            query = query.filter(User.clinic_id == clinic_id)
    else:
        query = select(User, Clinic.name).join(Clinic, User.clinic_id == Clinic.id).filter(
            User.clinic_id == current_user.clinic_id
        )
    
    # Filter by active status (show all for SuperAdmin, only active for others)
    if not is_super:
        query = query.filter(User.is_active == True)
    
    if role:
        query = query.filter(User.role == role)
    
    query = query.order_by(User.first_name, User.last_name)
    
    result = await db.execute(query)
    users_data = result.all()
    
    users_list = []
    for user, clinic_name in users_data:
        user_dict = UserListResponse.model_validate(user).model_dump()
        user_dict["clinic_name"] = clinic_name
        user_dict["clinic_id"] = user.clinic_id
        users_list.append(user_dict)
    
    return users_list


class UserCreateRequest(BaseModel):
    username: str
    email: str
    password: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    role: UserRole
    clinic_id: Optional[int] = None  # Allow SuperAdmin to specify clinic_id


class UserUpdateRequest(BaseModel):
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[UserRole] = None
    password: Optional[str] = None  # Optional password field
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

    # Use provided clinic_id or fallback to current_user's clinic_id
    # SuperAdmin can create users for any clinic by providing clinic_id
    target_clinic_id = payload.clinic_id if payload.clinic_id else current_user.clinic_id
    
    new_user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        first_name=payload.first_name or "",
        last_name=payload.last_name or "",
        role=payload.role,
        clinic_id=target_clinic_id,
        is_active=True,
        is_verified=False,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    # Load clinic name for response
    from app.models import Clinic
    clinic_result = await db.execute(select(Clinic).where(Clinic.id == new_user.clinic_id))
    clinic = clinic_result.scalar_one_or_none()
    
    response = UserListResponse.model_validate(new_user)
    if clinic:
        response.clinic_name = clinic.name
    response.clinic_id = new_user.clinic_id
    
    return response


@router.patch("/{user_id}", response_model=UserListResponse)
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    current_user: User = Depends(RoleChecker([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_async_session),
):
    # Check if SuperAdmin
    is_super = await is_super_admin(current_user, db)
    
    # SuperAdmin can update users from any clinic, others only from their clinic
    if is_super:
        query = select(User).where(User.id == user_id)
    else:
        query = select(User).where(and_(User.id == user_id, User.clinic_id == current_user.clinic_id))
    
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check email uniqueness if being updated
    if payload.email is not None and payload.email != user.email:
        exists = await db.execute(select(User).where(User.email == payload.email))
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already exists")
        user.email = payload.email
    
    if payload.first_name is not None:
        user.first_name = payload.first_name
    if payload.last_name is not None:
        user.last_name = payload.last_name
    if payload.role is not None:
        user.role = payload.role
    if payload.password is not None:
        # Only update password if provided
        if len(payload.password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
        user.hashed_password = hash_password(payload.password)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_verified is not None:
        user.is_verified = payload.is_verified

    await db.commit()
    await db.refresh(user)
    
    # Load clinic name for response
    from app.models import Clinic
    clinic_result = await db.execute(select(Clinic).where(Clinic.id == user.clinic_id))
    clinic = clinic_result.scalar_one_or_none()
    
    response = UserListResponse.model_validate(user)
    if clinic:
        response.clinic_name = clinic.name
    response.clinic_id = user.clinic_id
    
    return response


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: User = Depends(RoleChecker([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete a user from the database (hard delete).
    SuperAdmin can delete users from any clinic, others only from their clinic.
    """
    # Check if SuperAdmin
    is_super = await is_super_admin(current_user, db)
    
    # SuperAdmin can delete users from any clinic, others only from their clinic
    if is_super:
        query = select(User).where(User.id == user_id)
    else:
        query = select(User).where(and_(User.id == user_id, User.clinic_id == current_user.clinic_id))
    
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    # Hard delete - remove user from database
    # Need to handle related records that may reference this user
    # Use SQL directly to avoid ORM relationship loading issues
    from sqlalchemy import text
    
    # Helper function to safely execute SQL for optional tables
    async def safe_execute_optional(query: str, params: dict, table_name: str):
        """Execute SQL query for optional table, skip if table doesn't exist"""
        try:
            await db.execute(text(query), params)
        except Exception as e:
            error_msg = str(e).lower()
            # If table doesn't exist, PostgreSQL aborts the transaction
            # We need to rollback and restart the transaction
            if "does not exist" in error_msg or "undefinedtable" in error_msg:
                # Rollback to clear the aborted transaction
                await db.rollback()
                # Restart transaction by executing a simple query
                await db.execute(text("SELECT 1"))
                return  # Table doesn't exist, skip
            # If transaction is aborted for other reasons, rollback and re-raise
            if "aborted" in error_msg or "in failed sql transaction" in error_msg:
                await db.rollback()
                # Restart transaction
                await db.execute(text("SELECT 1"))
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Erro ao processar {table_name}: Transação abortada. Erro: {str(e)}"
                )
            # For any other error, re-raise to be handled by outer exception handler
            raise
    
    try:
        # Delete related records that reference this user
        # Order matters: delete child records before parent records
        
        # 1. Delete user settings (optional - table might not exist)
        await safe_execute_optional(
            "DELETE FROM user_settings WHERE user_id = :user_id",
            {"user_id": user_id},
            "user_settings"
        )
        
        # 2. Delete voice sessions (optional - table might not exist)
        await safe_execute_optional(
            "DELETE FROM voice_sessions WHERE user_id = :user_id",
            {"user_id": user_id},
            "voice_sessions"
        )
        
        # 3. Clear references in payments (optional - table might not exist)
        await safe_execute_optional(
            "UPDATE payments SET created_by = NULL WHERE created_by = :user_id",
            {"user_id": user_id},
            "payments"
        )
        
        # 4. Clear references in preauth_requests (optional - table might not exist)
        await safe_execute_optional(
            "UPDATE preauth_requests SET creator_id = NULL WHERE creator_id = :user_id",
            {"user_id": user_id},
            "preauth_requests"
        )
        
        # 5. Clear references in appointments (doctor_id) - set to NULL
        # This is a critical table, so we'll handle errors differently
        try:
            await db.execute(
                text("UPDATE appointments SET doctor_id = NULL WHERE doctor_id = :user_id"),
                {"user_id": user_id}
            )
        except Exception as e:
            error_msg = str(e).lower()
            if "does not exist" in error_msg or "undefinedtable" in error_msg:
                # Table doesn't exist, skip
                await db.rollback()
                await db.execute(text("SELECT 1"))
            else:
                raise
        
        # 6. Now delete the user
        await db.execute(
            text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )
        
        await db.commit()
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        await db.rollback()
        error_msg = str(e)
        
        # Check for foreign key constraint errors
        if "foreign key" in error_msg.lower() or "constraint" in error_msg.lower() or "violates foreign key" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não é possível excluir o usuário: existem registros relacionados que impedem a exclusão. Erro: {error_msg}"
            )
        
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error deleting user {user_id}: {error_msg}", exc_info=True)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao excluir usuário: {error_msg}"
        )
    
    return None  # 204 No Content

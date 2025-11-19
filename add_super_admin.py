"""
Script to add or update SuperAdmin user in the database
Ensures SuperAdmin user exists with correct role and permissions
"""
import asyncio
import sys
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from passlib.context import CryptContext

from app.models import User, Clinic
from app.models.menu import UserRole
from config import settings

# Initialize password context
try:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except Exception:
    # Fallback if bcrypt has issues
    pwd_context = CryptContext(schemes=["bcrypt"])


async def add_super_admin():
    """Add or update SuperAdmin user in the database"""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # Get SuperAdmin role
            result = await db.execute(
                select(UserRole).where(UserRole.name == "SuperAdmin")
            )
            superadmin_role = result.scalar_one_or_none()
            
            if not superadmin_role:
                print("❌ SuperAdmin role not found. Please run seed_menu_data.py first.")
                return
            
            # Check if SuperAdmin user already exists
            result = await db.execute(
                select(User).where(User.username == "superadmin")
            )
            existing_admin = result.scalar_one_or_none()
            
            # Get or create a default clinic
            clinic_result = await db.execute(select(Clinic).limit(1))
            clinic = clinic_result.scalar_one_or_none()
            
            if not clinic:
                clinic = Clinic(
                    name="Default Clinic",
                    legal_name="Default Clinic",
                    tax_id="00000000000000",
                    is_active=True
                )
                db.add(clinic)
                await db.flush()
                print("  ✓ Created default clinic")
            
            if existing_admin:
                # Update existing SuperAdmin user
                print(f"  Found existing SuperAdmin user (ID: {existing_admin.id})")
                
                updated = False
                if existing_admin.role_id != superadmin_role.id:
                    existing_admin.role_id = superadmin_role.id
                    updated = True
                    print("  ✓ Updated role_id to SuperAdmin")
                
                if existing_admin.role != "admin":
                    existing_admin.role = "admin"
                    updated = True
                    print("  ✓ Updated role to admin")
                
                if not existing_admin.is_active:
                    existing_admin.is_active = True
                    updated = True
                    print("  ✓ Activated user")
                
                if not existing_admin.is_verified:
                    existing_admin.is_verified = True
                    updated = True
                    print("  ✓ Verified user")
                
                if existing_admin.clinic_id != clinic.id:
                    existing_admin.clinic_id = clinic.id
                    updated = True
                    print(f"  ✓ Updated clinic_id to {clinic.id}")
                
                if not existing_admin.permissions or existing_admin.permissions.get("all") != True:
                    existing_admin.permissions = {"all": True}
                    updated = True
                    print("  ✓ Updated permissions to full access")
                
                if updated:
                    await db.commit()
                    print("  ✅ SuperAdmin user updated successfully!")
                else:
                    print("  ✅ SuperAdmin user already has correct configuration")
                
                print(f"\n  SuperAdmin Information:")
                print(f"    Username: {existing_admin.username}")
                print(f"    Email: {existing_admin.email}")
                print(f"    Role ID: {existing_admin.role_id} (SuperAdmin)")
                print(f"    Clinic ID: {existing_admin.clinic_id}")
                print(f"    Active: {existing_admin.is_active}")
                print(f"    Verified: {existing_admin.is_verified}")
                print(f"    Permissions: {existing_admin.permissions}")
            else:
                # Create new SuperAdmin user
                print("  Creating new SuperAdmin user...")
                
                superadmin_user = User(
                    username="superadmin",
                    email="admin@prontivus.com",
                    hashed_password=pwd_context.hash("admin123"),  # Change this in production!
                    first_name="Super",
                    last_name="Admin",
                    role="admin",  # Legacy enum
                    role_id=superadmin_role.id,
                    clinic_id=clinic.id,
                    is_active=True,
                    is_verified=True,
                    permissions={"all": True}  # Full permissions
                )
                db.add(superadmin_user)
                await db.commit()
                await db.refresh(superadmin_user)
                
                print("  ✅ SuperAdmin user created successfully!")
                print(f"\n  SuperAdmin Information:")
                print(f"    Username: {superadmin_user.username}")
                print(f"    Email: {superadmin_user.email}")
                print(f"    Password: admin123 (⚠️  CHANGE IN PRODUCTION!)")
                print(f"    Role ID: {superadmin_user.role_id} (SuperAdmin)")
                print(f"    Clinic ID: {superadmin_user.clinic_id}")
                print(f"    Active: {superadmin_user.is_active}")
                print(f"    Verified: {superadmin_user.is_verified}")
                print(f"    Permissions: {superadmin_user.permissions}")
            
        except Exception as e:
            await db.rollback()
            print(f"\n❌ Error adding SuperAdmin: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    print("Adding SuperAdmin user to database...\n")
    asyncio.run(add_super_admin())


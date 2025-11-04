"""
Seed Database with Test Data
Run this script to populate the database with sample clinics and users for testing
"""

import asyncio
from sqlalchemy import select
from database import AsyncSessionLocal
from app.models import Clinic, User, UserRole
from app.core.auth import hash_password


async def seed_database():
    """Seed the database with test data"""
    async with AsyncSessionLocal() as session:
        print("🌱 Starting database seed...")
        
        # Check if clinic already exists
        query = select(Clinic).where(Clinic.name == "HealthCare Plus")
        result = await session.execute(query)
        clinic = result.scalar_one_or_none()
        
        if not clinic:
            # Create a test clinic
            clinic = Clinic(
                name="HealthCare Plus",
                legal_name="HealthCare Plus Medical Services LTDA",
                tax_id="12.345.678/0001-90",
                address="123 Medical St, Suite 100, Health City, HC 12345",
                phone="+1 (555) 123-4567",
                email="contact@healthcareplus.com",
                is_active=True
            )
            session.add(clinic)
            await session.commit()
            await session.refresh(clinic)
            print(f"✅ Created clinic: {clinic.name} (ID: {clinic.id})")
        else:
            print(f"✅ Clinic already exists: {clinic.name} (ID: {clinic.id})")
        
        # Create test users
        users_data = [
            {
                "username": "admin",
                "email": "admin@clinic.com",
                "password": "admin123",
                "first_name": "Admin",
                "last_name": "User",
                "role": UserRole.ADMIN,
            },
            {
                "username": "secretary",
                "email": "secretary@clinic.com",
                "password": "secretary123",
                "first_name": "Sarah",
                "last_name": "Secretary",
                "role": UserRole.SECRETARY,
            },
            {
                "username": "dr.smith",
                "email": "dr.smith@clinic.com",
                "password": "doctor123",
                "first_name": "John",
                "last_name": "Smith",
                "role": UserRole.DOCTOR,
            },
            {
                "username": "dr.jones",
                "email": "dr.jones@clinic.com",
                "password": "doctor123",
                "first_name": "Emily",
                "last_name": "Jones",
                "role": UserRole.DOCTOR,
            },
            {
                "username": "patient1",
                "email": "patient@example.com",
                "password": "patient123",
                "first_name": "Michael",
                "last_name": "Patient",
                "role": UserRole.PATIENT,
            },
        ]
        
        for user_data in users_data:
            # Check if user already exists
            query = select(User).where(User.username == user_data["username"])
            result = await session.execute(query)
            existing_user = result.scalar_one_or_none()
            
            if not existing_user:
                user = User(
                    username=user_data["username"],
                    email=user_data["email"],
                    hashed_password=hash_password(user_data["password"]),
                    first_name=user_data["first_name"],
                    last_name=user_data["last_name"],
                    role=user_data["role"],
                    clinic_id=clinic.id,
                    is_active=True,
                    is_verified=True
                )
                session.add(user)
                await session.commit()
                print(f"✅ Created user: {user.username} ({user.role.value}) - Password: {user_data['password']}")
            else:
                print(f"⏭️  User already exists: {user_data['username']}")
        
        print("\n" + "="*50)
        print("🎉 Database seeding completed!")
        print("="*50)
        print("\n📝 Test Credentials:\n")
        print("Admin:")
        print("  Email: admin@clinic.com")
        print("  Password: admin123")
        print("\nSecretary:")
        print("  Email: secretary@clinic.com")
        print("  Password: secretary123")
        print("\nDoctor:")
        print("  Email: dr.smith@clinic.com")
        print("  Password: doctor123")
        print("\nPatient:")
        print("  Email: patient@example.com")
        print("  Password: patient123")
        print("\n" + "="*50)


if __name__ == "__main__":
    asyncio.run(seed_database())


#!/usr/bin/env python3
"""
Script to reset a user's password in the database
Usage: python reset_user_password.py <email> [new_password]
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import AsyncSessionLocal, engine
from app.models import User
from app.core.security import hash_password


async def reset_user_password(email: str, new_password: str = None):
    """
    Reset a user's password
    
    Args:
        email: User email address
        new_password: New password (if not provided, will generate one)
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find user by email
            query = select(User).where(User.email == email.lower())
            result = await db.execute(query)
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"❌ User with email '{email}' not found in database.")
                print("\nAvailable users:")
                # List all users
                all_users_query = select(User).order_by(User.email)
                all_result = await db.execute(all_users_query)
                all_users = all_result.scalars().all()
                
                if all_users:
                    print(f"\n{'Email':<40} {'Username':<20} {'Role':<15} {'Active':<10}")
                    print("-" * 85)
                    for u in all_users:
                        print(f"{u.email:<40} {u.username:<20} {str(u.role):<15} {'Yes' if u.is_active else 'No'}")
                else:
                    print("  No users found in database.")
                return False
            
            # Generate password if not provided
            if not new_password:
                import secrets
                import string
                alphabet = string.ascii_letters + string.digits
                new_password = ''.join(secrets.choice(alphabet) for _ in range(12))
            
            # Hash the new password
            hashed_password = hash_password(new_password)
            
            # Update user password
            user.hashed_password = hashed_password
            await db.commit()
            await db.refresh(user)
            
            print("=" * 70)
            print("✅ Password reset successful!")
            print("=" * 70)
            print(f"\nUser Information:")
            print(f"  Email:      {user.email}")
            print(f"  Username:   {user.username}")
            print(f"  Name:       {user.full_name}")
            print(f"  Role:       {user.role}")
            print(f"  Active:     {'Yes' if user.is_active else 'No'}")
            print(f"  Verified:   {'Yes' if user.is_verified else 'No'}")
            print(f"\n🔑 New Password: {new_password}")
            print("\n⚠️  IMPORTANT: Save this password securely. It cannot be retrieved again.")
            print("=" * 70)
            
            return True
            
        except Exception as e:
            await db.rollback()
            print(f"❌ Error resetting password: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python reset_user_password.py <email> [new_password]")
        print("\nExample:")
        print("  python reset_user_password.py patient@prontivus.com")
        print("  python reset_user_password.py patient@prontivus.com MyNewPassword123")
        sys.exit(1)
    
    email = sys.argv[1]
    new_password = sys.argv[2] if len(sys.argv) > 2 else None
    
    if new_password and len(new_password) < 8:
        print("❌ Error: Password must be at least 8 characters long")
        sys.exit(1)
    
    success = await reset_user_password(email, new_password)
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


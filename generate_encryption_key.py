#!/usr/bin/env python3
"""
Generate encryption key for API keys
Run this script to generate a secure encryption key for storing API keys
"""

from cryptography.fernet import Fernet

def generate_key():
    """Generate a new encryption key"""
    key = Fernet.generate_key()
    return key.decode()

if __name__ == "__main__":
    key = generate_key()
    print("=" * 60)
    print("ENCRYPTION KEY GENERATED")
    print("=" * 60)
    print(f"\n{key}\n")
    print("=" * 60)
    print("Add this to your .env file:")
    print(f"ENCRYPTION_KEY={key}")
    print("=" * 60)
    print("\n⚠️  IMPORTANT: Keep this key secure and never commit it to version control!")
    print("   Store it in a secure location and use environment variables in production.\n")


#!/usr/bin/env python3
"""
Generate a secure secret key for production use
"""
import secrets

if __name__ == "__main__":
    secret_key = secrets.token_urlsafe(32)
    print(f"Generated SECRET_KEY:")
    print(secret_key)
    print(f"\nAdd this to your Render environment variables:")
    print(f"SECRET_KEY={secret_key}")


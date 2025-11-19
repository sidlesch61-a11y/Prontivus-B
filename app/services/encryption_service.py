"""
Encryption Service for sensitive data (API keys, etc.)
Uses Fernet (symmetric encryption) from cryptography library
"""

import os
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64

# Get encryption key from environment or use default (for development only)
# In production, this should be set via environment variable
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    # Generate a key for development (DO NOT USE IN PRODUCTION)
    # In production, generate once and store securely:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    print("WARNING: Using auto-generated encryption key. Set ENCRYPTION_KEY environment variable in production!")

# Initialize Fernet cipher
try:
    cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
except Exception as e:
    print(f"ERROR: Failed to initialize encryption. Using no-op encryption: {e}")
    cipher = None


def encrypt(plaintext: str) -> Optional[str]:
    """
    Encrypt a plaintext string
    
    Args:
        plaintext: The string to encrypt
        
    Returns:
        Encrypted string (base64 encoded) or None if encryption fails
    """
    if not plaintext:
        return None
    
    if not cipher:
        # Fallback: return plaintext if encryption is not available (development only)
        print("WARNING: Encryption not available, storing plaintext!")
        return plaintext
    
    try:
        encrypted_bytes = cipher.encrypt(plaintext.encode())
        return base64.b64encode(encrypted_bytes).decode()
    except Exception as e:
        print(f"ERROR: Encryption failed: {e}")
        return None


def decrypt(encrypted_text: str) -> Optional[str]:
    """
    Decrypt an encrypted string
    
    Args:
        encrypted_text: The encrypted string (base64 encoded)
        
    Returns:
        Decrypted plaintext string or None if decryption fails
    """
    if not encrypted_text:
        return None
    
    if not cipher:
        # Fallback: return as-is if encryption is not available
        return encrypted_text
    
    try:
        encrypted_bytes = base64.b64decode(encrypted_text.encode())
        decrypted_bytes = cipher.decrypt(encrypted_bytes)
        return decrypted_bytes.decode()
    except Exception as e:
        print(f"ERROR: Decryption failed: {e}")
        return None


def generate_key() -> str:
    """
    Generate a new encryption key
    
    Returns:
        Base64-encoded encryption key
    """
    return Fernet.generate_key().decode()


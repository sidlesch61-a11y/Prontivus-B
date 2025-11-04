"""
Security and data validation utilities
"""

import re
from typing import Optional
from pydantic import validator, Field
import phonenumbers
from phonenumbers import NumberParseException


def validate_cpf(cpf: str) -> str:
    """
    Validate Brazilian CPF format and checksum
    """
    if not cpf:
        return cpf
    
    # Remove non-numeric characters
    cpf = re.sub(r'\D', '', cpf)
    
    # Check length
    if len(cpf) != 11:
        raise ValueError('CPF must have 11 digits')
    
    # Check for invalid patterns (all same digits)
    if cpf == cpf[0] * 11:
        raise ValueError('Invalid CPF: all digits are the same')
    
    # Validate checksum
    def calculate_digit(cpf_digits, weights):
        total = sum(int(digit) * weight for digit, weight in zip(cpf_digits, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder
    
    # First digit
    first_digit = calculate_digit(cpf[:9], range(10, 1, -1))
    if int(cpf[9]) != first_digit:
        raise ValueError('Invalid CPF: first checksum digit is incorrect')
    
    # Second digit
    second_digit = calculate_digit(cpf[:10], range(11, 1, -1))
    if int(cpf[10]) != second_digit:
        raise ValueError('Invalid CPF: second checksum digit is incorrect')
    
    return cpf


def validate_phone(phone: str) -> str:
    """
    Validate international phone number format
    """
    if not phone:
        return phone
    
    # Remove all non-numeric characters except +
    cleaned_phone = re.sub(r'[^\d+]', '', phone)
    
    try:
        # Parse the phone number
        parsed_number = phonenumbers.parse(cleaned_phone, None)
        
        # Check if it's a valid number
        if not phonenumbers.is_valid_number(parsed_number):
            raise ValueError('Invalid phone number')
        
        # Return in international format
        return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
    
    except NumberParseException:
        raise ValueError('Invalid phone number format')


def validate_email(email: str) -> str:
    """
    Validate email format
    """
    if not email:
        return email
    
    # Basic email regex pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        raise ValueError('Invalid email format')
    
    # Check for suspicious patterns
    if '..' in email or email.startswith('.') or email.endswith('.'):
        raise ValueError('Invalid email format')
    
    # Check length limits
    if len(email) > 254:
        raise ValueError('Email too long')
    
    local_part, domain = email.rsplit('@', 1)
    if len(local_part) > 64:
        raise ValueError('Email local part too long')
    
    return email.lower()


def validate_password_strength(password: str) -> str:
    """
    Validate password strength
    """
    if len(password) < 8:
        raise ValueError('Password must be at least 8 characters long')
    
    if len(password) > 128:
        raise ValueError('Password too long')
    
    # Check for at least one uppercase letter
    if not re.search(r'[A-Z]', password):
        raise ValueError('Password must contain at least one uppercase letter')
    
    # Check for at least one lowercase letter
    if not re.search(r'[a-z]', password):
        raise ValueError('Password must contain at least one lowercase letter')
    
    # Check for at least one digit
    if not re.search(r'\d', password):
        raise ValueError('Password must contain at least one digit')
    
    # Check for at least one special character
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValueError('Password must contain at least one special character')
    
    # Check for common weak passwords
    weak_passwords = [
        'password', '123456', '123456789', 'qwerty', 'abc123',
        'password123', 'admin', 'letmein', 'welcome', 'monkey'
    ]
    
    if password.lower() in weak_passwords:
        raise ValueError('Password is too common, please choose a stronger password')
    
    return password


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """
    Sanitize user input to prevent XSS and other attacks
    """
    if not text:
        return text
    
    # Limit length
    if len(text) > max_length:
        text = text[:max_length]
    
    # Remove or escape potentially dangerous characters
    dangerous_chars = ['<', '>', '"', "'", '&', '\x00', '\r', '\n']
    for char in dangerous_chars:
        text = text.replace(char, '')
    
    # Remove excessive whitespace
    text = ' '.join(text.split())
    
    return text.strip()


def validate_file_upload(filename: str, content_type: str, max_size: int = 10 * 1024 * 1024) -> tuple[str, str]:
    """
    Validate file upload for security
    """
    # Allowed file extensions
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx', '.txt'}
    
    # Get file extension
    file_ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    if file_ext not in allowed_extensions:
        raise ValueError(f'File type {file_ext} not allowed')
    
    # Check content type
    allowed_content_types = {
        'image/jpeg', 'image/png', 'image/gif', 'application/pdf',
        'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain'
    }
    
    if content_type not in allowed_content_types:
        raise ValueError(f'Content type {content_type} not allowed')
    
    # Sanitize filename
    safe_filename = re.sub(r'[^\w\-_\.]', '', filename)
    if not safe_filename:
        raise ValueError('Invalid filename')
    
    return safe_filename, content_type

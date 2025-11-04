"""
Security configuration and constants
"""

from typing import List, Dict, Any
from enum import Enum

# Security levels
class SecurityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

# Rate limiting configuration
RATE_LIMITS = {
    "login": {
        "requests_per_minute": 5,
        "requests_per_hour": 20,
        "lockout_duration_minutes": 15
    },
    "api": {
        "requests_per_minute": 100,
        "requests_per_hour": 1000
    },
    "data_export": {
        "requests_per_hour": 10,
        "requests_per_day": 50
    }
}

# Password requirements
PASSWORD_REQUIREMENTS = {
    "min_length": 8,
    "max_length": 128,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_digits": True,
    "require_special_chars": True,
    "forbidden_patterns": [
        "password", "123456", "qwerty", "abc123",
        "admin", "letmein", "welcome", "monkey"
    ]
}

# JWT configuration
JWT_CONFIG = {
    "access_token_expire_minutes": 30,
    "refresh_token_expire_days": 7,
    "algorithm": "HS256",
    "issuer": "prontivus-api",
    "audience": "prontivus-frontend"
}

# CORS configuration
CORS_CONFIG = {
    "allowed_origins": [
        "http://localhost:3000",
        "https://prontivus.com",
        "https://www.prontivus.com"
    ],
    "allowed_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    "allowed_headers": [
        "Authorization",
        "Content-Type",
        "X-Requested-With",
        "Accept",
        "Origin",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers"
    ],
    "allow_credentials": True,
    "max_age": 3600
}

# Content Security Policy
CSP_CONFIG = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-inline' 'unsafe-eval'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: https:",
    "font-src": "'self' data:",
    "connect-src": "'self'",
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "object-src": "'none'",
    "media-src": "'self'",
    "worker-src": "'self'"
}

# File upload security
FILE_UPLOAD_CONFIG = {
    "max_file_size": 10 * 1024 * 1024,  # 10MB
    "allowed_extensions": [
        ".jpg", ".jpeg", ".png", ".gif", ".pdf",
        ".doc", ".docx", ".txt", ".csv", ".xlsx"
    ],
    "allowed_mime_types": [
        "image/jpeg", "image/png", "image/gif",
        "application/pdf", "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain", "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ],
    "scan_for_malware": True,
    "quarantine_suspicious": True
}

# Database security
DATABASE_SECURITY = {
    "connection_pool_size": 20,
    "connection_pool_overflow": 30,
    "connection_pool_timeout": 30,
    "connection_pool_recycle": 3600,
    "encrypt_connections": True,
    "audit_logging": True
}

# Session security
SESSION_CONFIG = {
    "cookie_name": "prontivus_session",
    "cookie_secure": True,
    "cookie_httponly": True,
    "cookie_samesite": "strict",
    "session_timeout_minutes": 30,
    "max_sessions_per_user": 3
}

# Logging configuration
SECURITY_LOGGING = {
    "log_level": "INFO",
    "log_format": "json",
    "log_file": "logs/security.log",
    "max_file_size": 100 * 1024 * 1024,  # 100MB
    "backup_count": 10,
    "events_to_log": [
        "login_attempts",
        "data_exports",
        "patient_data_changes",
        "admin_actions",
        "security_violations",
        "api_errors"
    ]
}

# Input validation
INPUT_VALIDATION = {
    "max_string_length": 1000,
    "max_text_length": 10000,
    "sanitize_html": True,
    "validate_sql_injection": True,
    "validate_xss": True,
    "validate_path_traversal": True
}

# API security
API_SECURITY = {
    "require_https": True,
    "rate_limit_by_ip": True,
    "rate_limit_by_user": True,
    "log_all_requests": True,
    "validate_content_type": True,
    "max_request_size": 10 * 1024 * 1024,  # 10MB
    "timeout_seconds": 30
}

# Audit trail configuration
AUDIT_TRAIL = {
    "enabled": True,
    "retention_days": 365,
    "sensitive_fields": [
        "password", "ssn", "cpf", "credit_card",
        "bank_account", "medical_record"
    ],
    "events_to_audit": [
        "user_login",
        "user_logout",
        "data_create",
        "data_update",
        "data_delete",
        "data_export",
        "admin_action",
        "security_event"
    ]
}

# Encryption configuration
ENCRYPTION_CONFIG = {
    "algorithm": "AES-256-GCM",
    "key_rotation_days": 90,
    "encrypt_sensitive_data": True,
    "sensitive_fields": [
        "cpf", "phone", "email", "address",
        "medical_notes", "allergies"
    ]
}

# Backup security
BACKUP_SECURITY = {
    "encrypt_backups": True,
    "backup_retention_days": 30,
    "backup_location": "secure_storage",
    "test_restore_monthly": True,
    "offsite_backup": True
}

# Monitoring and alerting
MONITORING_CONFIG = {
    "enable_monitoring": True,
    "alert_on_failed_logins": True,
    "alert_on_data_exports": True,
    "alert_on_admin_actions": True,
    "alert_thresholds": {
        "failed_logins_per_hour": 10,
        "data_exports_per_day": 20,
        "api_errors_per_hour": 50
    }
}

# Compliance settings
COMPLIANCE_CONFIG = {
    "gdpr_compliant": True,
    "hipaa_compliant": True,
    "data_retention_policy": "7_years",
    "right_to_be_forgotten": True,
    "data_portability": True,
    "consent_management": True
}

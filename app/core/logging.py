"""
Structured logging configuration for security and monitoring
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import Request
from config import settings

# Configure structured logging
class SecurityLogger:
    """Custom logger for security events"""
    
    def __init__(self):
        self.logger = logging.getLogger("security")
        self.logger.setLevel(logging.INFO)
        
        # Create console handler with JSON formatter
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
    
    def log_login_attempt(
        self,
        username: str,
        ip_address: str,
        user_agent: str,
        success: bool,
        failure_reason: Optional[str] = None,
        user_id: Optional[int] = None
    ):
        """Log login attempts"""
        event = {
            "event_type": "login_attempt",
            "timestamp": datetime.utcnow().isoformat(),
            "username": username,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "success": success,
            "failure_reason": failure_reason,
            "user_id": user_id,
            "severity": "INFO" if success else "WARNING"
        }
        self.logger.info(json.dumps(event))
    
    def log_data_export(
        self,
        user_id: int,
        username: str,
        export_type: str,
        record_count: int,
        ip_address: str,
        filters: Optional[Dict[str, Any]] = None
    ):
        """Log data export activities"""
        event = {
            "event_type": "data_export",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "username": username,
            "export_type": export_type,
            "record_count": record_count,
            "ip_address": ip_address,
            "filters": filters,
            "severity": "INFO"
        }
        self.logger.info(json.dumps(event))
    
    def log_patient_data_change(
        self,
        user_id: int,
        username: str,
        patient_id: int,
        change_type: str,
        field_changed: str,
        old_value: Any,
        new_value: Any,
        ip_address: str
    ):
        """Log critical patient data changes"""
        event = {
            "event_type": "patient_data_change",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "username": username,
            "patient_id": patient_id,
            "change_type": change_type,
            "field_changed": field_changed,
            "old_value": str(old_value) if old_value is not None else None,
            "new_value": str(new_value) if new_value is not None else None,
            "ip_address": ip_address,
            "severity": "WARNING"
        }
        self.logger.warning(json.dumps(event))
    
    def log_security_event(
        self,
        event_type: str,
        user_id: Optional[int],
        username: Optional[str],
        ip_address: str,
        description: str,
        severity: str = "WARNING",
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """Log general security events"""
        event = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "username": username,
            "ip_address": ip_address,
            "description": description,
            "severity": severity,
            "additional_data": additional_data
        }
        
        if severity == "ERROR":
            self.logger.error(json.dumps(event))
        elif severity == "WARNING":
            self.logger.warning(json.dumps(event))
        else:
            self.logger.info(json.dumps(event))
    
    def log_api_access(
        self,
        request: Request,
        user_id: Optional[int],
        username: Optional[str],
        response_status: int,
        processing_time: float
    ):
        """Log API access for monitoring"""
        event = {
            "event_type": "api_access",
            "timestamp": datetime.utcnow().isoformat(),
            "method": request.method,
            "url": str(request.url),
            "user_id": user_id,
            "username": username,
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "response_status": response_status,
            "processing_time_ms": round(processing_time * 1000, 2),
            "severity": "ERROR" if response_status >= 400 else "INFO"
        }
        self.logger.info(json.dumps(event))


# Global security logger instance
security_logger = SecurityLogger()


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request"""
    # Check for forwarded headers (behind proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fallback to direct connection
    return request.client.host if request.client else "unknown"


def log_request(request: Request, user_id: Optional[int] = None, username: Optional[str] = None):
    """Log incoming request for monitoring"""
    # This would be called from middleware
    pass


def log_response(request: Request, response_status: int, processing_time: float, user_id: Optional[int] = None, username: Optional[str] = None):
    """Log API response for monitoring"""
    security_logger.log_api_access(
        request=request,
        user_id=user_id,
        username=username,
        response_status=response_status,
        processing_time=processing_time
    )

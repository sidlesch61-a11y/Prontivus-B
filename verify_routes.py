#!/usr/bin/env python3
"""
Verification script to check if AI and Fiscal config routes are available
Run this after restarting the backend server to verify routes are loaded
"""

import requests
import sys

API_URL = "http://localhost:8000"

def check_route(method, path, description):
    """Check if a route is available"""
    try:
        url = f"{API_URL}{path}"
        response = requests.request(method, url, timeout=2)
        if response.status_code == 404:
            print(f"✗ {description}: 404 Not Found")
            return False
        elif response.status_code == 401 or response.status_code == 403:
            print(f"✓ {description}: Route exists (auth required - {response.status_code})")
            return True
        else:
            print(f"✓ {description}: Route exists (status {response.status_code})")
            return True
    except requests.exceptions.ConnectionError:
        print(f"✗ {description}: Cannot connect to server (is it running?)")
        return False
    except Exception as e:
        print(f"✗ {description}: Error - {e}")
        return False

def main():
    print("Verifying AI and Fiscal Config routes...")
    print("=" * 60)
    
    routes = [
        ("GET", "/api/v1/ai-config", "AI Config GET"),
        ("PUT", "/api/v1/ai-config", "AI Config PUT"),
        ("POST", "/api/v1/ai-config/test-connection", "AI Config Test Connection"),
        ("GET", "/api/v1/ai-config/stats", "AI Config Stats"),
        ("GET", "/api/v1/fiscal-config", "Fiscal Config GET"),
        ("PUT", "/api/v1/fiscal-config", "Fiscal Config PUT"),
        ("POST", "/api/v1/fiscal-config/test-connection", "Fiscal Config Test Connection"),
        ("GET", "/api/v1/fiscal-config/stats", "Fiscal Config Stats"),
        ("POST", "/api/v1/fiscal-config/upload-certificate", "Fiscal Config Upload Certificate"),
        ("GET", "/api/v1/fiscal-config/documents", "Fiscal Config Documents"),
    ]
    
    results = []
    for method, path, description in routes:
        results.append(check_route(method, path, description))
    
    print("=" * 60)
    if all(results):
        print("✓ All routes are available!")
        return 0
    else:
        print("✗ Some routes are missing. Please restart the backend server.")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)


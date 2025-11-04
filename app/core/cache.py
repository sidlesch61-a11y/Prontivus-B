"""
Simple in-memory TTL cache for analytics responses.
Not suitable for multi-process deployment; replace with Redis in production.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional, Tuple


class TTLCache:
    def __init__(self, default_ttl_seconds: int = 300) -> None:
        self._store: dict[str, Tuple[float, Any]] = {}
        self._default_ttl = default_ttl_seconds

    def _now(self) -> float:
        return time.time()

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if self._now() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        self._store[key] = (self._now() + ttl, value)

    def cached(self, key_builder: Callable[..., str], ttl_seconds: Optional[int] = None):
        def decorator(func: Callable[..., Any]):
            def wrapper(*args, **kwargs):
                key = key_builder(*args, **kwargs)
                hit = self.get(key)
                if hit is not None:
                    return hit
                value = func(*args, **kwargs)
                self.set(key, value, ttl_seconds)
                return value
            return wrapper
        return decorator


# Global cache instance for analytics
analytics_cache = TTLCache(default_ttl_seconds=300)



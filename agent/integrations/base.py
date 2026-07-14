"""Base integration with caching and rate limiting."""

from datetime import datetime, timedelta
from typing import Any, Callable


class IntegrationCache:
    """Simple in-memory TTL cache per integration."""

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[Any, datetime]] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        if key not in self._store:
            return None
        value, expires = self._store[key]
        if datetime.now() > expires:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int | None = None):
        ttl = ttl or self.default_ttl
        self._store[key] = (value, datetime.now() + timedelta(seconds=ttl))

    def clear(self):
        self._store.clear()


class RateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, max_calls: int = 10, window: int = 60):
        self.max_calls = max_calls
        self.window = window
        self._calls: list[datetime] = []

    def allow(self) -> bool:
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window)
        self._calls = [t for t in self._calls if t > cutoff]
        if len(self._calls) >= self.max_calls:
            return False
        self._calls.append(now)
        return True


def tool_fn(name: str, doc: str, fn: Callable) -> Callable:
    """Wrap a function with proper name and docstring for tool registration."""
    fn.__name__ = name
    fn.__doc__ = doc
    return fn

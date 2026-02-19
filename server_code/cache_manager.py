"""
cache_manager.py - Thread-safe TTL cache for server-side data
=============================================================
Replaces ad-hoc global dict caches throughout the codebase with a proper
thread-safe implementation that includes:
- TTL-based expiration
- Maximum size with LRU eviction
- Thread-safe via threading.Lock
- Simple invalidation API
"""

import threading
import time
import logging

logger = logging.getLogger(__name__)


class TTLCache:
    """Thread-safe in-memory cache with TTL and max size."""

    def __init__(self, ttl_seconds=180, max_size=100, name='cache'):
        self._cache = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._name = name

    def get(self, key):
        """Get a cached value. Returns None if expired or missing."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() - entry['ts'] >= self._ttl:
                del self._cache[key]
                return None
            return entry['value']

    def set(self, key, value):
        """Set a cached value. Evicts oldest if at max size."""
        with self._lock:
            # Evict oldest if at capacity (and not updating existing)
            if key not in self._cache and len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k]['ts'])
                del self._cache[oldest_key]
            self._cache[key] = {'value': value, 'ts': time.time()}

    def invalidate(self, key=None):
        """Invalidate a specific key or all keys if key is None."""
        with self._lock:
            if key is not None:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

    def size(self):
        """Return current cache size."""
        with self._lock:
            return len(self._cache)

    def __repr__(self):
        return f"TTLCache(name='{self._name}', ttl={self._ttl}s, max_size={self._max_size}, current={self.size()})"


# =========================================================
# Pre-configured cache instances for use by other modules
# =========================================================

# Dashboard data cache (follow-up reminders, etc.)
dashboard_cache = TTLCache(ttl_seconds=180, max_size=50, name='dashboard')

# Tags cache (client tags)
tags_cache = TTLCache(ttl_seconds=30, max_size=10, name='tags')

# Report cache (financial reports, etc.)
report_cache = TTLCache(ttl_seconds=300, max_size=20, name='reports')

# FX rate cache (exchange rates)
fx_rate_cache = TTLCache(ttl_seconds=3600, max_size=10, name='fx_rates')

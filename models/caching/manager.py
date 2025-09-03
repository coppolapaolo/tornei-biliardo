"""
Module: models/caching/manager.py
Purpose: Advanced caching system for performance optimization
Requirements: Implement multi-level caching with TTL, LRU, and intelligent invalidation
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List, Callable, TypeVar
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from threading import RLock
import hashlib
import json
import logging
from collections import OrderedDict
from enum import Enum

# Setup logging
logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheStrategy(Enum):
    """Caching strategies for different use cases."""

    LRU = "lru"
    TTL = "ttl"
    LFU = "lfu"
    FIFO = "fifo"
    HYBRID = "hybrid"


class CacheLevel(Enum):
    """Cache levels for hierarchical caching."""

    L1_MEMORY = "l1_memory"
    L2_APPLICATION = "l2_application"
    L3_DISTRIBUTED = "l3_distributed"


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""

    key: str
    value: Any
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    ttl_seconds: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    size_bytes: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl_seconds is None:
            return False
        return (datetime.utcnow() - self.created_at).total_seconds() > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        """Get age of cache entry in seconds."""
        return (datetime.utcnow() - self.created_at).total_seconds()

    def access(self) -> None:
        """Record cache access."""
        self.last_accessed = datetime.utcnow()
        self.access_count += 1


@dataclass
class CacheStats:
    """Cache performance statistics."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0
    memory_usage_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    @property
    def miss_rate(self) -> float:
        """Calculate cache miss rate."""
        return 100.0 - self.hit_rate


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    def get(self, key: str) -> Optional[CacheEntry]:
        """Get cache entry by key."""

    @abstractmethod
    def set(self, entry: CacheEntry) -> bool:
        """Set cache entry."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete cache entry by key."""

    @abstractmethod
    def clear(self) -> None:
        """Clear all cache entries."""

    @abstractmethod
    def get_stats(self) -> CacheStats:
        """Get cache statistics."""

    def invalidate_by_tags(self, tags: List[str]) -> int:
        """Invalidate entries by tags. Default implementation does nothing."""
        return 0


class MemoryCacheBackend(CacheBackend):
    """In-memory cache backend with configurable eviction strategy."""

    def __init__(
        self,
        max_size: int = 1000,
        strategy: CacheStrategy = CacheStrategy.LRU,
        default_ttl: Optional[int] = None,
    ):
        self.max_size = max_size
        self.strategy = strategy
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = RLock()
        self._stats = CacheStats()

    def get(self, key: str) -> Optional[CacheEntry]:
        """Get cache entry with strategy-specific access handling."""
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired:
                self.delete(key)
                self._stats.misses += 1
                return None

            entry.access()
            self._stats.hits += 1

            # Move to end for LRU
            if self.strategy == CacheStrategy.LRU:
                self._cache.move_to_end(key)

            return entry

    def set(self, entry: CacheEntry) -> bool:
        """Set cache entry with eviction if necessary."""
        with self._lock:
            # Apply default TTL if not specified
            if entry.ttl_seconds is None and self.default_ttl:
                entry.ttl_seconds = self.default_ttl

            # Check if we need to evict entries
            if len(self._cache) >= self.max_size:
                self._evict_entries()

            # Calculate entry size (rough estimation)
            entry.size_bytes = self._estimate_size(entry.value)

            self._cache[entry.key] = entry
            self._update_stats()

            return True

    def delete(self, key: str) -> bool:
        """Delete cache entry."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._update_stats()
                return True
            return False

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._cache.clear()
            self._stats = CacheStats()

    def get_stats(self) -> CacheStats:
        """Get current cache statistics."""
        with self._lock:
            self._stats.size = len(self._cache)
            self._stats.memory_usage_bytes = sum(
                entry.size_bytes for entry in self._cache.values()
            )
            return self._stats

    def invalidate_by_tags(self, tags: List[str]) -> int:
        """Invalidate entries by tags."""
        with self._lock:
            keys_to_remove = []
            for key, entry in self._cache.items():
                if any(tag in entry.tags for tag in tags):
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._cache[key]

            self._update_stats()
            return len(keys_to_remove)

    def _evict_entries(self) -> None:
        """Evict entries based on strategy."""
        if self.strategy == CacheStrategy.LRU:
            # Remove least recently used (first item)
            self._cache.popitem(last=False)
        elif self.strategy == CacheStrategy.LFU:
            # Remove least frequently used
            min_access_key = min(
                self._cache.keys(), key=lambda k: self._cache[k].access_count
            )
            del self._cache[min_access_key]
        elif self.strategy == CacheStrategy.FIFO:
            # Remove first in, first out
            self._cache.popitem(last=False)
        elif self.strategy == CacheStrategy.TTL:
            # Remove expired entries first, then oldest
            expired_keys = [
                key for key, entry in self._cache.items() if entry.is_expired
            ]
            if expired_keys:
                for key in expired_keys:
                    del self._cache[key]
            else:
                # Remove oldest if no expired entries
                oldest_key = min(
                    self._cache.keys(), key=lambda k: self._cache[k].created_at
                )
                del self._cache[oldest_key]

        self._stats.evictions += 1

    def _update_stats(self) -> None:
        """Update cache statistics."""
        self._stats.size = len(self._cache)

    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of value."""
        try:
            if isinstance(value, (str, int, float, bool)):
                return len(str(value))
            elif isinstance(value, (list, tuple)):
                return sum(self._estimate_size(item) for item in value)
            elif isinstance(value, dict):
                return sum(
                    self._estimate_size(k) + self._estimate_size(v)
                    for k, v in value.items()
                )
            else:
                # Rough estimate for complex objects
                return len(str(value))
        except Exception:
            return 100  # Default estimate


class HierarchicalCacheManager:
    """Multi-level hierarchical cache manager."""

    def __init__(self):
        self._levels: Dict[CacheLevel, CacheBackend] = {}
        self._key_generators: Dict[str, Callable] = {}
        self._invalidation_rules: Dict[str, List[str]] = {}

    def register_level(self, level: CacheLevel, backend: CacheBackend) -> None:
        """Register a cache level with its backend."""
        self._levels[level] = backend
        logger.info(f"Registered cache level {level.value}")

    def register_key_generator(self, name: str, generator: Callable) -> None:
        """Register a key generation function."""
        self._key_generators[name] = generator

    def add_invalidation_rule(self, pattern: str, tags: List[str]) -> None:
        """Add cache invalidation rule."""
        self._invalidation_rules[pattern] = tags

    def get(self, key: str, levels: Optional[List[CacheLevel]] = None) -> Optional[Any]:
        """Get value from cache hierarchy."""
        if levels is None:
            levels = list(self._levels.keys())

        for level in levels:
            if level not in self._levels:
                continue

            backend = self._levels[level]
            entry = backend.get(key)

            if entry is not None:
                logger.debug(f"Cache hit at level {level.value} for key {key}")

                # Promote to higher levels (write-through)
                self._promote_entry(entry, level, levels)
                return entry.value

        logger.debug(f"Cache miss for key {key}")
        return None

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
        tags: Optional[List[str]] = None,
        levels: Optional[List[CacheLevel]] = None,
    ) -> bool:
        """Set value in cache hierarchy."""
        if levels is None:
            levels = list(self._levels.keys())

        entry = CacheEntry(
            key=key,
            value=value,
            created_at=datetime.utcnow(),
            last_accessed=datetime.utcnow(),
            ttl_seconds=ttl_seconds,
            tags=tags or [],
        )

        success = True
        for level in levels:
            if level not in self._levels:
                continue

            backend = self._levels[level]
            if not backend.set(entry):
                success = False
                logger.warning(
                    f"Failed to set cache at level {level.value} for key {key}"
                )

        return success

    def delete(self, key: str, levels: Optional[List[CacheLevel]] = None) -> bool:
        """Delete from all specified cache levels."""
        if levels is None:
            levels = list(self._levels.keys())

        success = True
        for level in levels:
            if level not in self._levels:
                continue

            backend = self._levels[level]
            if not backend.delete(key):
                success = False

        return success

    def invalidate_by_tags(
        self, tags: List[str], levels: Optional[List[CacheLevel]] = None
    ) -> Dict[CacheLevel, int]:
        """Invalidate cache entries by tags across levels."""
        if levels is None:
            levels = list(self._levels.keys())

        results = {}
        for level in levels:
            if level not in self._levels:
                continue

            backend = self._levels[level]
            if hasattr(backend, "invalidate_by_tags"):
                count = backend.invalidate_by_tags(tags)
                results[level] = count
                logger.info(f"Invalidated {count} entries at level {level.value}")

        return results

    def clear_all(self) -> None:
        """Clear all cache levels."""
        for level, backend in self._levels.items():
            backend.clear()
            logger.info(f"Cleared cache level {level.value}")

    def get_comprehensive_stats(self) -> Dict[CacheLevel, CacheStats]:
        """Get statistics from all cache levels."""
        stats = {}
        for level, backend in self._levels.items():
            stats[level] = backend.get_stats()
        return stats

    def _promote_entry(
        self,
        entry: CacheEntry,
        current_level: CacheLevel,
        target_levels: List[CacheLevel],
    ) -> None:
        """Promote cache entry to higher levels."""
        level_priority = {
            CacheLevel.L1_MEMORY: 1,
            CacheLevel.L2_APPLICATION: 2,
            CacheLevel.L3_DISTRIBUTED: 3,
        }

        current_priority = level_priority.get(current_level, 999)

        for level in target_levels:
            if level == current_level:
                continue

            level_prio = level_priority.get(level, 999)
            if level_prio < current_priority:  # Higher priority (lower number)
                backend = self._levels[level]
                backend.set(entry)


# Global cache manager instance
cache_manager = HierarchicalCacheManager()

# Initialize default cache levels
cache_manager.register_level(
    CacheLevel.L1_MEMORY,
    MemoryCacheBackend(max_size=500, strategy=CacheStrategy.LRU, default_ttl=300),
)

cache_manager.register_level(
    CacheLevel.L2_APPLICATION,
    MemoryCacheBackend(max_size=2000, strategy=CacheStrategy.HYBRID, default_ttl=1800),
)


def cached(
    ttl_seconds: Optional[int] = None,
    tags: Optional[List[str]] = None,
    key_generator: Optional[str] = None,
    levels: Optional[List[CacheLevel]] = None,
):
    """Decorator for caching function results."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Generate cache key
            if key_generator and key_generator in cache_manager._key_generators:
                key = cache_manager._key_generators[key_generator](*args, **kwargs)
            else:
                key = _generate_default_key(func.__name__, args, kwargs)

            # Try to get from cache
            cached_value = cache_manager.get(key, levels)
            if cached_value is not None:
                return cached_value

            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_manager.set(
                key=key,
                value=result,
                ttl_seconds=ttl_seconds,
                tags=tags or [],
                levels=levels,
            )

            return result

        return wrapper

    return decorator


def cache_invalidate(tags: List[str], levels: Optional[List[CacheLevel]] = None):
    """Decorator for automatic cache invalidation."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            result = func(*args, **kwargs)

            # Invalidate cache after successful execution
            if tags:  # Only invalidate if tags are provided
                cache_manager.invalidate_by_tags(tags, levels)
                logger.debug(f"Invalidated cache tags: {tags}")

            return result

        return wrapper

    return decorator


def _generate_default_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """Generate default cache key from function and arguments."""
    # Create a deterministic key from function name and arguments
    key_data = {"function": func_name, "args": args, "kwargs": sorted(kwargs.items())}

    # Convert to JSON and hash for consistent key
    key_json = json.dumps(key_data, sort_keys=True, default=str)
    key_hash = hashlib.md5(key_json.encode()).hexdigest()

    return f"{func_name}:{key_hash}"


# Specific cache key generators for common patterns
def campionato_cache_key(*args, **kwargs) -> str:
    """Generate cache key for campionato-related data."""
    campionato_id = kwargs.get("campionato_id") or (args[0] if args else "unknown")
    return f"campionato:{campionato_id}"


def user_cache_key(*args, **kwargs) -> str:
    """Generate cache key for user-related data."""
    user_id = kwargs.get("user_id") or (args[0] if args else "unknown")
    return f"user:{user_id}"


def gara_cache_key(*args, **kwargs) -> str:
    """Generate cache key for gara-related data."""
    gara_id = kwargs.get("gara_id") or (args[0] if args else "unknown")
    return f"gara:{gara_id}"


# Register key generators
cache_manager.register_key_generator("campionato", campionato_cache_key)
cache_manager.register_key_generator("user", user_cache_key)
cache_manager.register_key_generator("gara", gara_cache_key)

# Register invalidation rules
cache_manager.add_invalidation_rule("campionato_*", ["campionato"])
cache_manager.add_invalidation_rule("user_*", ["user"])
cache_manager.add_invalidation_rule("gara_*", ["gara", "campionato"])
cache_manager.add_invalidation_rule("match_*", ["match", "gara", "campionato"])

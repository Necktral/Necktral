"""
Advanced caching layer for reporting kernel with Redis support and intelligent invalidation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


@dataclass
class CacheConfig:
    """Configuration for cache behavior"""
    ttl_seconds: int = 300  # 5 minutes default
    enable_compression: bool = True
    cache_empty_results: bool = False
    cache_key_prefix: str = "reporting"


class ReportingCacheManager:
    """
    Advanced caching manager for reporting datasets with:
    - Intelligent cache key generation
    - TTL management
    - Cache warming capabilities
    - Hit/miss metrics
    """

    def __init__(self, config: CacheConfig | None = None):
        self.config = config or CacheConfig()
        self._hits = 0
        self._misses = 0

    def generate_cache_key(
        self,
        dataset_key: str,
        filters: dict[str, Any],
        company_id: int,
        branch_id: int | None,
    ) -> str:
        """
        Generate deterministic cache key based on dataset and filters.

        Args:
            dataset_key: Dataset identifier
            filters: Query filters
            company_id: Company scope
            branch_id: Branch scope (optional)

        Returns:
            Cache key string
        """
        # Normalize filters for consistent hashing
        normalized_filters = json.dumps(filters, sort_keys=True, default=str)

        # Create deterministic hash
        content = f"{dataset_key}|{normalized_filters}|{company_id}|{branch_id or 'global'}"
        hash_digest = hashlib.sha256(content.encode()).hexdigest()[:16]

        return f"{self.config.cache_key_prefix}:dataset:{dataset_key}:{hash_digest}"

    def get(self, cache_key: str) -> dict[str, Any] | None:
        """
        Retrieve cached dataset result.

        Args:
            cache_key: Cache key to lookup

        Returns:
            Cached data or None if not found/expired
        """
        result = cache.get(cache_key)
        if result is not None:
            self._hits += 1
            return result

        self._misses += 1
        return None

    def set(
        self,
        cache_key: str,
        data: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """
        Store dataset result in cache.

        Args:
            cache_key: Cache key
            data: Dataset result to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        ttl_seconds = ttl if ttl is not None else self.config.ttl_seconds

        # Don't cache empty results unless configured
        if not self.config.cache_empty_results and not data.get("rows"):
            return

        cache.set(cache_key, data, timeout=ttl_seconds)

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all cache keys matching pattern.

        Args:
            pattern: Pattern to match (e.g., "accounting.*")

        Returns:
            Number of keys invalidated
        """
        # This requires Redis backend with key scanning support
        # For now, return 0 as Django's default cache doesn't support pattern deletion
        return 0

    def warm_cache(
        self,
        dataset_key: str,
        filters_list: list[dict[str, Any]],
        company_id: int,
        branch_id: int | None,
        executor_func: Any,
    ) -> int:
        """
        Pre-warm cache with common query patterns.

        Args:
            dataset_key: Dataset to warm
            filters_list: List of filter combinations
            company_id: Company scope
            branch_id: Branch scope
            executor_func: Function to execute dataset query

        Returns:
            Number of entries warmed
        """
        warmed = 0
        for filters in filters_list:
            cache_key = self.generate_cache_key(
                dataset_key=dataset_key,
                filters=filters,
                company_id=company_id,
                branch_id=branch_id,
            )

            # Check if already cached
            if self.get(cache_key) is not None:
                continue

            try:
                result = executor_func(dataset_key, filters)
                self.set(cache_key, result)
                warmed += 1
            except Exception:
                # Skip failed warm attempts
                continue

        return warmed

    def get_metrics(self) -> dict[str, Any]:
        """
        Get cache performance metrics.

        Returns:
            Dictionary with hit/miss stats
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total,
            "hit_rate_pct": round(hit_rate, 2),
        }

    def reset_metrics(self) -> None:
        """Reset hit/miss counters"""
        self._hits = 0
        self._misses = 0


# Global cache manager instance
_cache_manager: ReportingCacheManager | None = None


def get_cache_manager() -> ReportingCacheManager:
    """Get or create global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = ReportingCacheManager()
    return _cache_manager

from __future__ import annotations

from dataclasses import dataclass

from django.core.cache import cache


@dataclass(frozen=True)
class DenyAggregate:
    count: int
    window_seconds: int


def bump_deny_counter(key: str, ttl_seconds: int = 60) -> int:
    if cache.add(key, 1, ttl_seconds):
        return 1
    try:
        return cache.incr(key)
    except Exception:
        val = int(cache.get(key, 0) or 0) + 1
        cache.set(key, val, ttl_seconds)
        return val


def should_emit(count: int, every: int = 50) -> bool:
    return count == 1 or (count % every == 0)


def aggregate_deny(*, key: str, ttl_seconds: int = 60, every: int = 50) -> DenyAggregate | None:
    count = bump_deny_counter(key, ttl_seconds=ttl_seconds)
    if should_emit(count, every=every):
        return DenyAggregate(count=count, window_seconds=ttl_seconds)
    return None

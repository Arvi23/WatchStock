"""Tiny in-process TTL cache for home-screen widgets (indices, movers, market news)."""

import time
from collections.abc import Callable
from typing import Any

_entries: dict[str, tuple[float, Any]] = {}


def get_or_set(key: str, ttl_seconds: float, produce: Callable[[], Any]) -> Any:
    """Return the cached value for `key`, or call `produce()` and cache its result.

    Exceptions from `produce` propagate and nothing is cached.
    """
    now = time.monotonic()
    hit = _entries.get(key)
    if hit and now - hit[0] < ttl_seconds:
        return hit[1]
    value = produce()
    _entries[key] = (now, value)
    return value


def clear() -> None:
    _entries.clear()

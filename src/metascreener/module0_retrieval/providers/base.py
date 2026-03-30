"""Abstract base class for bibliographic database search providers."""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod

from pydantic import BaseModel

from metascreener.module0_retrieval.models import BooleanQuery, RawRecord


class RateLimit(BaseModel):
    """Rate limit configuration for a search provider."""

    requests_per_second: float = 10.0


class TokenBucketLimiter:
    """Async token bucket rate limiter with burst support."""

    def __init__(self, rate: float, burst: int = 10) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            await asyncio.sleep(1.0 / self._rate)


class SearchProvider(ABC):
    """Abstract base for bibliographic database search providers."""

    @abstractmethod
    async def search(self, query: BooleanQuery, max_results: int = 10000) -> list[RawRecord]: ...

    @abstractmethod
    async def fetch_metadata(self, ids: list[str]) -> list[RawRecord]: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def rate_limit(self) -> RateLimit: ...

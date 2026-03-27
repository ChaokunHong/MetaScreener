"""Unit tests for SearchProvider ABC and RateLimit."""
from __future__ import annotations
import asyncio
import time
import pytest

def test_rate_limit_model():
    from metascreener.module0_retrieval.providers.base import RateLimit
    rl = RateLimit(requests_per_second=10.0)
    assert rl.requests_per_second == 10.0

@pytest.mark.asyncio
async def test_token_bucket_allows_burst():
    from metascreener.module0_retrieval.providers.base import TokenBucketLimiter
    limiter = TokenBucketLimiter(rate=10.0, burst=10)
    for _ in range(10):
        await limiter.acquire()

@pytest.mark.asyncio
async def test_token_bucket_throttles():
    from metascreener.module0_retrieval.providers.base import TokenBucketLimiter
    limiter = TokenBucketLimiter(rate=100.0, burst=1)
    await limiter.acquire()
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.005

def test_search_provider_is_abstract():
    from metascreener.module0_retrieval.providers.base import SearchProvider
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        SearchProvider()

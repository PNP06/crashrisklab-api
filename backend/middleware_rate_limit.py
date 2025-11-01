from __future__ import annotations

import os
import time
from typing import Callable, Dict, Tuple

from fastapi import Request, Response, HTTPException


class TokenBucket:
    def __init__(self, rate_per_min: int) -> None:
        self.capacity = max(1, int(rate_per_min))
        self.tokens = float(self.capacity)
        self.updated = time.time()

    def allow(self) -> bool:
        now = time.time()
        # refill per minute
        elapsed = max(0.0, now - self.updated)
        refill = (elapsed / 60.0) * self.capacity
        self.tokens = min(self.capacity, self.tokens + refill)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


_BUCKETS: Dict[str, TokenBucket] = {}


async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    rate = int(os.environ.get("RATE_LIMIT", "30") or "30")
    # key = API key if set, else client host
    api_key = request.headers.get("X-API-Key") or ""
    key = api_key or (request.client.host if request.client else "unknown")
    bucket = _BUCKETS.get(key)
    if bucket is None:
        bucket = _BUCKETS[key] = TokenBucket(rate)
    if not bucket.allow():
        corr_id = getattr(request.state, "corr_id", "")
        raise HTTPException(status_code=429, detail={"error": "rate limit", "corr_id": corr_id})
    return await call_next(request)


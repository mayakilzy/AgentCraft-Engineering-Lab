"""Per-session rate limiting (G07/T26 + ADR-0003 Part B #6).

Per the architecture contract §9: "per-IP+session rate limit". The
contract requires `RATE_LIMIT_PER_MINUTE=60` enforced on the runs
endpoint. We implement a simple in-memory token-bucket per session_id.

The limiter is intentionally simple — no Redis, no distributed state.
For a single-process FastAPI deployment (the V1 architecture), this is
sufficient. When the app scales to multiple workers, a Redis-backed
limiter can be swapped in without changing the API.

The limiter is applied to POST /api/v1/experiments/{id}/runs (the
resource-intensive endpoint). Other endpoints are not rate-limited
beyond the standard HTTP middleware.
"""
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Dict, Tuple
import uuid

from app.config import Settings
from app.core.errors import AppError


class RateLimiter:
    """In-memory token-bucket rate limiter.

    Each session_id gets a bucket of `capacity` tokens, refilled at
    `rate` tokens per second. A request consumes 1 token. When the
    bucket is empty, the request is rejected with 429.

    The bucket state is a dict of (session_id) -> (tokens, last_refill).
    A background cleanup would prune stale buckets, but for V1 the
    dict stays small (bounded by the number of active sessions, which
    is bounded by the guest session TTL + the purge cron).
    """

    def __init__(self, rate_per_minute: int) -> None:
        self.rate = rate_per_minute / 60.0  # tokens per second
        self.capacity = rate_per_minute  # burst capacity = 1 minute of tokens
        self._buckets: Dict[uuid.UUID, Tuple[float, float]] = defaultdict(
            lambda: (self.capacity, time.monotonic())
        )
        self._lock = Lock()

    def acquire(self, session_id: uuid.UUID) -> None:
        """Consume 1 token for the given session. Raises 429 if empty."""
        with self._lock:
            tokens, last = self._buckets[session_id]
            now = time.monotonic()
            # Refill: tokens += elapsed * rate, capped at capacity.
            elapsed = now - last
            tokens = min(self.capacity, tokens + elapsed * self.rate)
            if tokens < 1.0:
                self._buckets[session_id] = (tokens, now)
                raise AppError(
                    "rate limit exceeded — try again in a few seconds",
                    status_code=429,
                    code="rate_limited",
                    details={
                        "session_id": str(session_id),
                        "limit_per_minute": self.capacity,
                    },
                )
            self._buckets[session_id] = (tokens - 1.0, now)


# Singleton limiter. The rate is read from settings at first use.
_limiter: RateLimiter | None = None


def get_rate_limiter(settings: Settings) -> RateLimiter:
    """Return the singleton rate limiter, initialized from settings."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(settings.rate_limit_per_minute)
    return _limiter


def reset_rate_limiter_for_tests() -> None:
    """Drop the singleton limiter. Used by tests only."""
    global _limiter
    _limiter = None

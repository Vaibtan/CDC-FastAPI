"""Token-bucket rate limiting middleware backed by Redis.

Each client (identified by IP) gets a bucket with a configurable rate.
Requests that exceed the budget receive HTTP 429.

The implementation uses a single Redis EVALSHA (Lua script) per request
for atomicity and minimal round-trips.
"""
import logging
import time

import redis.asyncio as aioredis
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Lua script: token-bucket consume.
# KEYS[1] = bucket key
# ARGV[1] = max_tokens (capacity)
# ARGV[2] = refill_rate (tokens/sec)
# ARGV[3] = now (epoch seconds, float as string)
# Returns: [allowed (0/1), remaining_tokens]
_LUA_SCRIPT = """
local key       = KEYS[1]
local capacity  = tonumber(ARGV[1])
local rate      = tonumber(ARGV[2])
local now       = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local last   = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last   = now
end

-- Refill
local elapsed = math.max(0, now - last)
tokens = math.min(capacity, tokens + elapsed * rate)
last = now

-- Try consume
if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'ts', last)
    redis.call('EXPIRE', key, math.ceil(capacity / rate) + 1)
    return {1, math.floor(tokens)}
else
    redis.call('HMSET', key, 'tokens', tokens, 'ts', last)
    redis.call('EXPIRE', key, math.ceil(capacity / rate) + 1)
    return {0, 0}
end
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP token-bucket rate limiter using Redis."""

    def __init__(
        self,
        app,
        *,
        capacity: int = 100,
        refill_rate: float = 10.0,
    ) -> None:
        super().__init__(app)
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._redis: aioredis.Redis | None = None
        self._script_sha: str | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url)
        return self._redis

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip health probes and metrics
        path = request.url.path
        if path.startswith("/api/v1/health") or path.startswith("/metrics"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        bucket_key = f"rl:{client_ip}"

        try:
            r = await self._get_redis()

            # Load script once
            if self._script_sha is None:
                self._script_sha = await r.script_load(_LUA_SCRIPT)

            result = await r.evalsha(
                self._script_sha,
                1,
                bucket_key,
                str(self.capacity),
                str(self.refill_rate),
                str(time.time()),
            )

            allowed, remaining = int(result[0]), int(result[1])

            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={
                        "Retry-After": str(int(1 / self.refill_rate) + 1),
                        "X-RateLimit-Limit": str(self.capacity),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(self.capacity)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response

        except Exception:
            # If Redis is down, fail open (allow the request)
            logger.debug("Rate-limit Redis unavailable, allowing request", exc_info=True)
            return await call_next(request)

import time
from collections import defaultdict, deque
from fastapi import Request
from fastapi.responses import JSONResponse
from .config import settings
LIMITS = {"/api/v1/auth": 20, "/api/v1/chat": 30, "/api/v1/jobs": 10, "default": 300}  # requests per minute
_hits: dict = defaultdict(deque)
def group(path):
    return next((g for g in LIMITS if g != "default" and path.startswith(g)), "default")
async def limiter(request: Request, call_next):
    if settings.rate_limit_enabled:
        g = group(request.url.path); k = (request.client.host if request.client else "?", g); q = _hits[k]; now = time.monotonic()
        while q and now - q[0] > 60: q.popleft()
        if len(q) >= LIMITS[g]:
            return JSONResponse(status_code=429, headers={"Retry-After": "60"}, content={"code": "rate_limited", "message": "Too many requests.", "details": None, "request_id": None})
        q.append(now)
    return await call_next(request)

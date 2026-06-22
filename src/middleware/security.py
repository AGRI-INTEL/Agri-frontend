"""
Security middleware for FastAPI
"""

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_MAX_TRACKED_IPS = 50_000


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to responses"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.scope.get("type") == "websocket":
            return await call_next(request)
        response = await call_next(request)

        is_docs = request.url.path.startswith((
            "/api/v1/docs", "/api/v1/redoc", "/api/v1/openapi.json"
        ))

        if is_docs:
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "object-src 'none'"
            )
        else:
            csp = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "object-src 'none'; "
                "frame-ancestors 'none'"
            )

        security_headers = {
            "Content-Security-Policy": csp,
            "X-Frame-Options": "SAMEORIGIN",
            "X-Content-Type-Options": "nosniff",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Permissions-Policy": (
                "geolocation=(), microphone=(), camera=(), "
                "payment=(), usb=(), magnetometer=(), gyroscope=(), "
                "accelerometer=(), ambient-light-sensor=(), autoplay=()"
            ),
            "Server": "AgriIntel360",
        }

        for header, value in security_headers.items():
            response.headers[header] = value

        if "server" in response.headers:
            del response.headers["server"]

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-process rate limiting — bounded memory, LRU eviction."""

    def __init__(self, app, requests_per_minute: int = 300):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        # {ip: [timestamp, ...]} — evicted when list empties or cap reached
        self.clients: dict[str, list] = {}

    def _evict_one_idle(self, current_time: float) -> None:
        """Remove the IP whose last request is oldest."""
        oldest_ip = min(
            self.clients,
            key=lambda ip: self.clients[ip][-1] if self.clients[ip] else 0,
        )
        del self.clients[oldest_ip]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        client_ip = request.client.host

        if (
            request.url.path.startswith("/health")
            or client_ip in {"127.0.0.1", "::1", "localhost"}
            or client_ip.startswith("10.")
            or client_ip.startswith("192.168.")
            or (client_ip.startswith("172.") and 16 <= int(client_ip.split(".")[1]) <= 31)
        ):
            return await call_next(request)

        current_time = time.time()
        cutoff = current_time - 60

        if client_ip not in self.clients:
            if len(self.clients) >= _MAX_TRACKED_IPS:
                self._evict_one_idle(current_time)
            self.clients[client_ip] = []

        # Purge old timestamps
        self.clients[client_ip] = [t for t in self.clients[client_ip] if t > cutoff]

        # Evict entry entirely when list is empty (saves memory)
        if not self.clients[client_ip] and client_ip in self.clients:
            # Keep it — we're about to add to it below; just skip the key to avoid
            # re-checking the cap. This path only fires on first request after idle.
            pass

        if len(self.clients[client_ip]) >= self.requests_per_minute:
            from starlette.responses import JSONResponse
            return JSONResponse(
                {"detail": "Too many requests. Please try again later."},
                status_code=429,
                headers={
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Reset": str(int(current_time + 60)),
                    "Retry-After": "60",
                },
            )

        self.clients[client_ip].append(current_time)

        # Evict the entry if it just became empty after the append (can't happen,
        # but guard for future changes) — skip. The cleanup runs on next request.

        response = await call_next(request)
        remaining = max(0, self.requests_per_minute - len(self.clients.get(client_ip, [])))
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(current_time + 60))
        return response


class CORSSecurityMiddleware(BaseHTTPMiddleware):
    """Enhanced CORS security middleware (kept for reference — not wired in main.py)."""

    def __init__(self, app, allowed_origins: list = None):
        super().__init__(app)
        self.allowed_origins = allowed_origins or []

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        origin = request.headers.get("origin")

        if origin and self.allowed_origins and origin not in self.allowed_origins:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Origin not allowed"
            )

        response = await call_next(request)

        if origin and (not self.allowed_origins or origin in self.allowed_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, Accept, Origin, User-Agent, "
                "Cache-Control, X-Requested-With"
            )
            response.headers["Access-Control-Max-Age"] = "86400"

        return response

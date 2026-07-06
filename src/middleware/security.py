"""
Security middleware for FastAPI
"""

import os
import time
import secrets
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_MAX_TRACKED_IPS = 50_000

SENSITIVE_PATHS = {"/auth/login", "/auth/register", "/auth/forgot-password"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection for state-changing requests."""

    def __init__(self, app, secret_key: str = None):
        super().__init__(app)
        self.secret_key = secret_key or os.urandom(32).hex()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            response = await call_next(request)
            if not request.cookies.get("csrf_token"):
                token = secrets.token_hex(32)
                response.set_cookie(
                    key="csrf_token",
                    value=token,
                    httponly=False,  # Required for double-submit JS to read it
                    samesite="lax",
                    secure=True,
                    max_age=86400,
                )
            return response

        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("X-CSRF-Token")

        if csrf_cookie and csrf_header and csrf_header == csrf_cookie:
            return await call_next(request)

        if request.headers.get("X-Requested-With"):
            return await call_next(request)

        from starlette.responses import JSONResponse
        if not csrf_cookie:
            return JSONResponse(
                {"detail": "CSRF token cookie missing. Refresh the page."},
                status_code=403,
            )
        return JSONResponse(
            {"detail": "CSRF token validation failed."},
            status_code=403,
        )


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
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
                "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net https://cdn.redoc.ly; "
                "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com; "
                "connect-src 'self' https://cdn.jsdelivr.net; "
                "worker-src 'self' blob:; "
                "object-src 'none'"
            )
            security_headers = {
                "Content-Security-Policy": csp,
                "X-Frame-Options": "SAMEORIGIN",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                "Permissions-Policy": (
                    "geolocation=(), microphone=(), camera=(), "
                    "payment=(), usb=(), magnetometer=(), gyroscope=(), "
                    "accelerometer=(), ambient-light-sensor=(), autoplay=()"
                ),
            }
        else:
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
                "img-src 'self' data: https:; "
                "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com; "
                "connect-src 'self' https://accounts.google.com https://login.microsoftonline.com https://cdn.jsdelivr.net; "
                "frame-src 'self' https://accounts.google.com; "
                "object-src 'none'; "
                "frame-ancestors 'none'"
            )
            security_headers = {
                "Content-Security-Policy": csp,
                "X-Frame-Options": "SAMEORIGIN",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                "Permissions-Policy": (
                    "geolocation=(), microphone=(), camera=(), "
                    "payment=(), usb=(), magnetometer=(), gyroscope=(), "
                    "accelerometer=(), ambient-light-sensor=(), autoplay=()"
                ),
            }

        for header, value in security_headers.items():
            response.headers[header] = value

        response.headers["server"] = ""
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-process rate limiting — bounded memory, LRU eviction.
    Differentiated limits per endpoint type.
    """

    SENSITIVE_LIMIT = 10
    DEFAULT_LIMIT = 300

    def __init__(self, app, requests_per_minute: int = 300):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.clients: dict[str, list] = {}

    def _get_limit_for_path(self, path: str) -> int:
        for sensitive in SENSITIVE_PATHS:
            if path.startswith(sensitive):
                return self.SENSITIVE_LIMIT
        return self.requests_per_minute

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

        client_ip = request.client.host if request.client else "127.0.0.1"

        if (
            request.url.path in {"/health", "/api/v1/health", "/"}
            or request.url.path.startswith(("/health", "/api/v1/health"))
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

        self.clients[client_ip] = [t for t in self.clients[client_ip] if t > cutoff]

        path_limit = self._get_limit_for_path(request.url.path)

        if len(self.clients[client_ip]) >= path_limit:
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
        path_limit = self._get_limit_for_path(request.url.path)
        remaining = max(0, path_limit - len(self.clients.get(client_ip, [])))
        response.headers["X-RateLimit-Limit"] = str(path_limit)
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

"""Response security headers suitable for the local HTTP and Vite build boundary."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

BASE_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    )
)


def _is_api_path(path: str, api_prefix: str) -> bool:
    return path == api_prefix or path.startswith(f"{api_prefix}/")


def apply_security_headers(
    headers: MutableHeaders,
    *,
    path: str,
    api_prefix: str = "/api",
) -> None:
    """Apply the shared policy, including to outer framework error responses."""
    if "server" in headers:
        del headers["server"]
    for name, value in BASE_SECURITY_HEADERS.items():
        headers[name] = value
    if _is_api_path(path, api_prefix):
        headers["Cache-Control"] = "no-store"
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type == "text/html":
        headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY


class SecurityHeadersMiddleware:
    """Apply deterministic headers without exposing an application Server header."""

    def __init__(self, app: ASGIApp, *, api_prefix: str = "/api") -> None:
        self.app = app
        self.api_prefix = api_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", ()))
                headers = MutableHeaders(scope=message)
                path = str(scope.get("path", ""))
                apply_security_headers(headers, path=path, api_prefix=self.api_prefix)
            await send(message)

        await self.app(scope, receive, send_with_security_headers)

"""Local development entry point for the AIWebNovel backend."""

import os

import uvicorn

from aiwebnovel.core.config import get_settings
from aiwebnovel.security.host import HostConfigurationError, validate_loopback_bind_host


def main() -> None:
    """Start the local-only development server."""
    configured_host = os.environ.get("AIWEBNOVEL_HOST", "127.0.0.1")
    try:
        validate_loopback_bind_host(configured_host)
    except HostConfigurationError as exc:
        raise SystemExit(
            "AIWebNovel refused to start because its host is not an explicit loopback address."
        ) from exc

    try:
        settings = get_settings()
    except Exception:  # noqa: BLE001 - the degraded ASGI app must still expose live.
        host = "127.0.0.1"
        port = 8000
        log_level = "info"
    else:
        host = settings.host
        port = settings.port
        log_level = settings.log_level.lower()
    uvicorn.run(
        "aiwebnovel.main:app",
        host=host,
        port=port,
        log_level=log_level,
        access_log=False,
        proxy_headers=False,
        forwarded_allow_ips="",
        server_header=False,
        reload=False,
    )


if __name__ == "__main__":
    main()

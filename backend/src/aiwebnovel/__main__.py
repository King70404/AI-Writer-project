"""Local development entry point for the AIWebNovel backend."""

import uvicorn

from aiwebnovel.core.config import get_settings


def main() -> None:
    """Start the local-only development server."""
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
        reload=False,
    )


if __name__ == "__main__":
    main()

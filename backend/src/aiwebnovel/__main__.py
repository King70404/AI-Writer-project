"""Local development entry point for the AIWebNovel backend."""

import uvicorn

from aiwebnovel.core.config import get_settings


def main() -> None:
    """Start the local-only development server."""
    settings = get_settings()
    uvicorn.run(
        "aiwebnovel.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=False,
        reload=False,
    )


if __name__ == "__main__":
    main()

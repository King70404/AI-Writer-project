"""Standard-library JSON logging with request-scoped correlation IDs."""

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

_LOGGER_NAME = "aiwebnovel"
_HANDLER_MARKER = "_aiwebnovel_json_handler"
_request_id: ContextVar[str | None] = ContextVar("aiwebnovel_request_id", default=None)


def get_request_id() -> str | None:
    """Return the request ID bound to the current execution context."""
    return _request_id.get()


def bind_request_id(request_id: str) -> Token[str | None]:
    """Bind a request ID and return the token needed to restore context."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the previous request context."""
    _request_id.reset(token)


class JsonFormatter(logging.Formatter):
    """Render one safe JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - arbitrary log arguments must not break logging.
            message = "Log message could not be formatted"

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }

        request_id = get_request_id()
        if request_id is not None:
            payload["request_id"] = request_id

        if record.exc_info:
            try:
                payload["exception"] = self.formatException(record.exc_info)
            except Exception:  # noqa: BLE001 - formatter extensions are an untrusted boundary.
                payload["exception"] = "Exception details could not be formatted"

        try:
            return json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError, OverflowError):
            fallback = {
                "timestamp": payload["timestamp"],
                "level": str(payload["level"]),
                "logger": str(payload["logger"]),
                "message": "Log record could not be serialized",
            }
            if request_id is not None:
                fallback["request_id"] = request_id
            return json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))


def _level_number(level: str | int) -> int:
    if isinstance(level, int):
        return level
    normalized = level.strip().upper()
    resolved = logging.getLevelName(normalized)
    if not isinstance(resolved, int):
        raise ValueError(f"Unsupported log level: {level!r}")
    return resolved


def configure_logging(level: str | int = "INFO") -> logging.Logger:
    """Configure exactly one JSON stdout handler for application loggers."""
    level_number = _level_number(level)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level_number)
    logger.propagate = False

    managed_handlers = [
        handler for handler in logger.handlers if getattr(handler, _HANDLER_MARKER, False)
    ]
    if managed_handlers:
        handler = managed_handlers[0]
        for duplicate in managed_handlers[1:]:
            logger.removeHandler(duplicate)
            duplicate.close()
    else:
        handler = logging.StreamHandler(sys.stdout)
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)

    handler.setLevel(level_number)
    handler.setFormatter(JsonFormatter())
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child of the managed application logger."""
    if name == _LOGGER_NAME or name.startswith(f"{_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")

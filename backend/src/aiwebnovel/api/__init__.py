"""Protocol-neutral HTTP helpers shared by bounded web adapters."""

from aiwebnovel.api.error_causes import has_database_driver_cause
from aiwebnovel.api.etags import (
    InvalidIfMatch,
    format_strong_etag,
    parse_strong_if_match,
)

__all__ = [
    "InvalidIfMatch",
    "format_strong_etag",
    "has_database_driver_cause",
    "parse_strong_if_match",
]

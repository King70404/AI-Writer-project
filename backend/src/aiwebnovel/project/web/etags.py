"""Project-compatible names for the shared strong ETag protocol."""

from aiwebnovel.api.etags import (
    InvalidIfMatch,
    format_strong_etag,
    parse_strong_if_match,
)

InvalidProjectIfMatch = InvalidIfMatch
format_project_etag = format_strong_etag
parse_project_if_match = parse_strong_if_match


__all__ = ["InvalidProjectIfMatch", "format_project_etag", "parse_project_if_match"]

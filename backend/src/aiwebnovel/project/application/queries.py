"""Immutable raw inputs for Project read use cases."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetProjectQuery:
    """Request the current snapshot for one externally represented Project ID."""

    project_id: str


__all__ = ["GetProjectQuery"]

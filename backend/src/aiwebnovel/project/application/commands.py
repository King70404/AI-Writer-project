"""Immutable raw inputs for Project write use cases."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateProjectCommand:
    """Request creation of a new Project with application-generated identifiers."""

    title: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class ReviseProjectCommand:
    """Replace the complete current Project title and description."""

    project_id: str
    expected_version: int
    title: str
    description: str = ""


__all__ = ["CreateProjectCommand", "ReviseProjectCommand"]

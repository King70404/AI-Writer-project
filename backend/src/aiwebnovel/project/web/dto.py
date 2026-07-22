"""Strict immutable HTTP DTOs for the Project API."""

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator


class _ProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    title: str
    description: str = ""


class CreateProjectRequest(_ProjectRequest):
    """Client-owned fields accepted when creating a Project."""


class ReviseProjectRequest(_ProjectRequest):
    """Complete client-owned replacement accepted for a Project revision."""


class ProjectResponse(BaseModel):
    """Detached current Project state exposed over HTTP."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime
    head_updated_at: datetime

    @field_validator(
        "created_at",
        "updated_at",
        "revision_created_at",
        "head_updated_at",
    )
    @classmethod
    def require_utc_datetime(cls, value: datetime) -> datetime:
        """Reject naive or non-UTC timestamps at the HTTP boundary."""
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("Project response timestamps must be aware UTC datetimes")
        return value


__all__ = ["CreateProjectRequest", "ProjectResponse", "ReviseProjectRequest"]

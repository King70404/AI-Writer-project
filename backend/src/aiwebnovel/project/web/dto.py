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


class DeleteProjectResponse(BaseModel):
    """Confirmation that an active Project has been logically deleted."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    deleted: bool


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
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("Project response timestamps must be aware UTC datetimes")
        return value


class ProjectListItemResponse(BaseModel):
    """Detached current-revision summary exposed by the list endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime

    @field_validator("created_at", "updated_at", "revision_created_at")
    @classmethod
    def require_utc_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("Project list timestamps must be aware UTC datetimes")
        return value


class ProjectListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    items: tuple[ProjectListItemResponse, ...]
    next_cursor: str | None
    has_more: bool


class ProjectRevisionHistoryItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    revision_id: str
    revision_number: int
    title: str
    created_at: datetime
    is_current: bool

    @field_validator("created_at")
    @classmethod
    def require_utc_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("Project revision timestamps must be aware UTC datetimes")
        return value


class ProjectRevisionHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: str
    current_revision_number: int
    items: tuple[ProjectRevisionHistoryItemResponse, ...]
    next_cursor: str | None
    has_more: bool


class ProjectRevisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: str
    revision_id: str
    revision_number: int
    title: str
    description: str
    created_at: datetime
    is_current: bool
    current_revision_number: int

    @field_validator("created_at")
    @classmethod
    def require_utc_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("Project revision timestamps must be aware UTC datetimes")
        return value


__all__ = [
    "CreateProjectRequest",
    "DeleteProjectResponse",
    "ProjectListItemResponse",
    "ProjectListResponse",
    "ProjectResponse",
    "ProjectRevisionHistoryItemResponse",
    "ProjectRevisionHistoryResponse",
    "ProjectRevisionResponse",
    "ReviseProjectRequest",
]

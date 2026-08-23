"""Safe novel-structure application and persistence failure mapping for HTTP."""

from typing import Literal, Never

from aiwebnovel.api.error_causes import has_database_driver_cause
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidDomainIdentifier
from aiwebnovel.novel_structure.errors import (
    ChapterAlreadyExists,
    ChapterNotFound,
    ChapterPositionConflict,
    ChapterVolumeOwnershipMismatch,
    InvalidNovelStructurePosition,
    InvalidNovelStructureSummary,
    InvalidNovelStructureTitle,
    NovelStructureDataCorruption,
    NovelStructureProjectNotFound,
    NovelStructureRepositoryError,
    OutlineAlreadyExists,
    OutlineNotFound,
    VolumeAlreadyExists,
    VolumeNotFound,
    VolumePositionConflict,
)
from aiwebnovel.project.errors import ProjectNotFound

Resource = Literal["outline", "volume", "chapter"]


def command_service_unavailable() -> AppError:
    return AppError(
        code="NOVEL_STRUCTURE_SERVICE_UNAVAILABLE",
        message="Novel structure command service is unavailable.",
        status_code=503,
        retryable=True,
    )


def query_service_unavailable() -> AppError:
    return AppError(
        code="NOVEL_STRUCTURE_QUERY_SERVICE_UNAVAILABLE",
        message="Novel structure query service is unavailable.",
        status_code=503,
        retryable=True,
    )


def _invalid_id(resource: str) -> AppError:
    return AppError(
        code=f"INVALID_{resource.upper()}_ID",
        message=f"The {resource.title()} identifier is invalid.",
        status_code=422,
    )


def invalid_project_id() -> AppError:
    return _invalid_id("project")


def invalid_outline_id() -> AppError:
    return _invalid_id("outline")


def invalid_volume_id() -> AppError:
    return _invalid_id("volume")


def invalid_chapter_id() -> AppError:
    return _invalid_id("chapter")


def precondition_required() -> AppError:
    return AppError(
        code="PRECONDITION_REQUIRED",
        message="A valid If-Match header is required.",
        status_code=428,
    )


def invalid_if_match() -> AppError:
    return AppError(
        code="INVALID_IF_MATCH",
        message="The If-Match header is invalid.",
        status_code=400,
    )


def unsupported_media_type() -> AppError:
    return AppError(
        code="UNSUPPORTED_MEDIA_TYPE",
        message="API request bodies must use UTF-8 JSON.",
        status_code=415,
    )


def raise_novel_structure_http_error(exc: Exception, *, resource: Resource) -> Never:
    if isinstance(exc, InvalidNovelStructureTitle):
        mapped = AppError(
            code="INVALID_NOVEL_STRUCTURE_TITLE",
            message="The novel structure title is invalid.",
            status_code=422,
            details={"field": "title"},
        )
    elif isinstance(exc, InvalidNovelStructureSummary):
        mapped = AppError(
            code="INVALID_NOVEL_STRUCTURE_SUMMARY",
            message="The novel structure summary is invalid.",
            status_code=422,
            details={"field": "summary"},
        )
    elif isinstance(exc, InvalidNovelStructurePosition):
        mapped = AppError(
            code="INVALID_NOVEL_STRUCTURE_POSITION",
            message="The novel structure position is invalid.",
            status_code=422,
            details={"field": "position"},
        )
    elif isinstance(exc, (ProjectNotFound, NovelStructureProjectNotFound)):
        mapped = AppError(
            code="PROJECT_NOT_FOUND",
            message="The Project was not found.",
            status_code=404,
        )
    elif isinstance(exc, OutlineNotFound):
        mapped = AppError(
            code="OUTLINE_NOT_FOUND", message="The Outline was not found.", status_code=404
        )
    elif isinstance(exc, VolumeNotFound):
        mapped = AppError(
            code="VOLUME_NOT_FOUND", message="The Volume was not found.", status_code=404
        )
    elif isinstance(exc, ChapterNotFound):
        mapped = AppError(
            code="CHAPTER_NOT_FOUND", message="The Chapter was not found.", status_code=404
        )
    elif isinstance(exc, OutlineAlreadyExists):
        mapped = AppError(
            code="OUTLINE_ALREADY_EXISTS",
            message="The Project already has an Outline or the identifier conflicts.",
            status_code=409,
        )
    elif isinstance(exc, VolumeAlreadyExists):
        mapped = AppError(
            code="VOLUME_ID_CONFLICT",
            message="The Volume identifier conflicts with stored data.",
            status_code=409,
        )
    elif isinstance(exc, ChapterAlreadyExists):
        mapped = AppError(
            code="CHAPTER_ID_CONFLICT",
            message="The Chapter identifier conflicts with stored data.",
            status_code=409,
        )
    elif isinstance(exc, VolumePositionConflict):
        mapped = AppError(
            code="VOLUME_POSITION_CONFLICT",
            message="The Volume position is already occupied.",
            status_code=409,
        )
    elif isinstance(exc, ChapterPositionConflict):
        mapped = AppError(
            code="CHAPTER_POSITION_CONFLICT",
            message="The Chapter position is already occupied.",
            status_code=409,
        )
    elif isinstance(exc, ChapterVolumeOwnershipMismatch):
        mapped = AppError(
            code="CHAPTER_VOLUME_OWNERSHIP_MISMATCH",
            message="The Volume does not belong to the Project.",
            status_code=409,
        )
    elif isinstance(exc, ConcurrencyConflict):
        mapped = AppError(
            code=f"{resource.upper()}_VERSION_CONFLICT",
            message=f"The {resource.title()} version does not match the current version.",
            status_code=412,
            details={
                "expected_version": exc.expected_version,
                "actual_version": exc.actual_version,
            },
        )
    elif isinstance(exc, NovelStructureDataCorruption) and has_database_driver_cause(exc):
        mapped = AppError(
            code="NOVEL_STRUCTURE_PERSISTENCE_UNAVAILABLE",
            message="Novel structure persistence is unavailable.",
            status_code=503,
            retryable=True,
        )
    elif isinstance(exc, NovelStructureDataCorruption):
        mapped = AppError(
            code="NOVEL_STRUCTURE_DATA_CORRUPTION",
            message="Stored novel structure data is unavailable.",
            status_code=500,
        )
    elif isinstance(exc, NovelStructureRepositoryError):
        mapped = AppError(
            code="NOVEL_STRUCTURE_PERSISTENCE_UNAVAILABLE",
            message="Novel structure persistence is unavailable.",
            status_code=503,
            retryable=True,
        )
    elif isinstance(exc, InvalidDomainIdentifier):
        mapped = _invalid_id(resource)
    else:
        raise exc
    raise mapped from exc


__all__ = [
    "command_service_unavailable",
    "invalid_chapter_id",
    "invalid_if_match",
    "invalid_outline_id",
    "invalid_project_id",
    "invalid_volume_id",
    "precondition_required",
    "query_service_unavailable",
    "raise_novel_structure_http_error",
    "unsupported_media_type",
]

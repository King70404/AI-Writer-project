"""Safe Story Bible application and persistence failure mapping for HTTP."""

from typing import Never

from aiwebnovel.api.error_causes import has_database_driver_cause
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidDomainIdentifier
from aiwebnovel.story_bible.application.errors import (
    StoryBibleForProjectNotFound,
    StoryBibleRevisionNotFound,
)
from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleContent,
    InvalidStoryBibleTitle,
    StoryBibleAlreadyExists,
    StoryBibleDataCorruption,
    StoryBibleForProjectAlreadyExists,
    StoryBibleNotFound,
    StoryBibleProjectNotFound,
    StoryBibleRepositoryError,
)


def story_bible_service_unavailable() -> AppError:
    return AppError(
        code="STORY_BIBLE_SERVICE_UNAVAILABLE",
        message="Story Bible service is unavailable.",
        status_code=503,
        retryable=True,
    )


def invalid_project_id() -> AppError:
    return AppError(
        code="INVALID_PROJECT_ID",
        message="The Project identifier is invalid.",
        status_code=422,
    )


def invalid_story_bible_id() -> AppError:
    return AppError(
        code="INVALID_STORY_BIBLE_ID",
        message="The Story Bible identifier is invalid.",
        status_code=422,
    )


def invalid_story_bible_revision_cursor() -> AppError:
    return AppError(
        code="INVALID_STORY_BIBLE_REVISION_CURSOR",
        message="The Story Bible revision cursor is invalid.",
        status_code=400,
    )


def invalid_story_bible_revision_history_request() -> AppError:
    return AppError(
        code="REQUEST_VALIDATION_ERROR",
        message="The Story Bible revision-history request is invalid.",
        status_code=422,
    )


def invalid_story_bible_revision_number() -> AppError:
    return AppError(
        code="INVALID_REVISION_NUMBER",
        message="The revision number is invalid.",
        status_code=422,
    )


def story_bible_history_service_unavailable() -> AppError:
    return AppError(
        code="STORY_BIBLE_HISTORY_SERVICE_UNAVAILABLE",
        message="Story Bible revision history is unavailable.",
        status_code=503,
        retryable=True,
    )


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


def raise_story_bible_http_error(exc: Exception) -> Never:
    """Translate known Story Bible failures and preserve unknown global 500s."""
    if isinstance(exc, InvalidStoryBibleTitle):
        mapped = AppError(
            code="INVALID_STORY_BIBLE_TITLE",
            message="The Story Bible title is invalid.",
            status_code=422,
            details={"field": "title"},
        )
    elif isinstance(exc, InvalidStoryBibleContent):
        mapped = AppError(
            code="INVALID_STORY_BIBLE_CONTENT",
            message="The Story Bible content is invalid.",
            status_code=422,
            details={"field": "content"},
        )
    elif isinstance(exc, StoryBibleForProjectNotFound):
        mapped = AppError(
            code="STORY_BIBLE_FOR_PROJECT_NOT_FOUND",
            message="The Project does not have a Story Bible.",
            status_code=404,
        )
    elif isinstance(exc, StoryBibleRevisionNotFound):
        mapped = AppError(
            code="STORY_BIBLE_REVISION_NOT_FOUND",
            message="The Story Bible revision was not found.",
            status_code=404,
        )
    elif isinstance(exc, StoryBibleProjectNotFound):
        mapped = AppError(
            code="PROJECT_NOT_FOUND",
            message="The Project was not found.",
            status_code=404,
        )
    elif isinstance(exc, StoryBibleNotFound):
        mapped = AppError(
            code="STORY_BIBLE_NOT_FOUND",
            message="The Story Bible was not found.",
            status_code=404,
        )
    elif isinstance(exc, StoryBibleForProjectAlreadyExists):
        mapped = AppError(
            code="STORY_BIBLE_ALREADY_EXISTS_FOR_PROJECT",
            message="The Project already has a Story Bible.",
            status_code=409,
        )
    elif isinstance(exc, StoryBibleAlreadyExists):
        mapped = AppError(
            code="STORY_BIBLE_ID_CONFLICT",
            message="The Story Bible identifier conflicts with stored data.",
            status_code=409,
        )
    elif isinstance(exc, ConcurrencyConflict):
        mapped = AppError(
            code="STORY_BIBLE_VERSION_CONFLICT",
            message="The Story Bible version does not match the current version.",
            status_code=412,
            details={
                "expected_version": exc.expected_version,
                "actual_version": exc.actual_version,
            },
        )
    elif isinstance(exc, StoryBibleDataCorruption) and has_database_driver_cause(exc):
        mapped = AppError(
            code="STORY_BIBLE_PERSISTENCE_UNAVAILABLE",
            message="Story Bible persistence is unavailable.",
            status_code=503,
            retryable=True,
        )
    elif isinstance(exc, StoryBibleDataCorruption):
        mapped = AppError(
            code="STORY_BIBLE_DATA_CORRUPTION",
            message="The stored Story Bible state is unavailable.",
            status_code=500,
        )
    elif isinstance(exc, StoryBibleRepositoryError):
        mapped = AppError(
            code="STORY_BIBLE_PERSISTENCE_UNAVAILABLE",
            message="Story Bible persistence is unavailable.",
            status_code=503,
            retryable=True,
        )
    elif isinstance(exc, InvalidDomainIdentifier):
        mapped = invalid_story_bible_id()
    else:
        raise exc
    raise mapped from exc


__all__ = [
    "invalid_if_match",
    "invalid_project_id",
    "invalid_story_bible_id",
    "invalid_story_bible_revision_cursor",
    "invalid_story_bible_revision_history_request",
    "invalid_story_bible_revision_number",
    "precondition_required",
    "raise_story_bible_http_error",
    "story_bible_history_service_unavailable",
    "story_bible_service_unavailable",
    "unsupported_media_type",
]

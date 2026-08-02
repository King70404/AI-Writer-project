"""Safe Character application and persistence failure mapping for HTTP."""

from typing import Never

from aiwebnovel.api.error_causes import has_database_driver_cause
from aiwebnovel.character.application.errors import CharacterRevisionNotFound
from aiwebnovel.character.errors import (
    CharacterAlreadyExists,
    CharacterDataCorruption,
    CharacterNotFound,
    CharacterProjectNotFound,
    CharacterRepositoryError,
    InvalidCharacterName,
    InvalidCharacterProfile,
    InvalidCharacterRole,
)
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidDomainIdentifier


def character_command_service_unavailable() -> AppError:
    return AppError(
        code="CHARACTER_SERVICE_UNAVAILABLE",
        message="Character command service is unavailable.",
        status_code=503,
        retryable=True,
    )


def character_query_service_unavailable() -> AppError:
    return AppError(
        code="CHARACTER_QUERY_SERVICE_UNAVAILABLE",
        message="Character query service is unavailable.",
        status_code=503,
        retryable=True,
    )


def invalid_project_id() -> AppError:
    return AppError(
        code="INVALID_PROJECT_ID",
        message="The Project identifier is invalid.",
        status_code=422,
    )


def invalid_character_id() -> AppError:
    return AppError(
        code="INVALID_CHARACTER_ID",
        message="The Character identifier is invalid.",
        status_code=422,
    )


def invalid_character_cursor() -> AppError:
    return AppError(
        code="INVALID_CHARACTER_CURSOR",
        message="The Character list cursor is invalid.",
        status_code=400,
    )


def invalid_character_revision_cursor() -> AppError:
    return AppError(
        code="INVALID_CHARACTER_REVISION_CURSOR",
        message="The Character revision cursor is invalid.",
        status_code=400,
    )


def invalid_character_revision_history_request() -> AppError:
    return AppError(
        code="REQUEST_VALIDATION_ERROR",
        message="The Character revision-history request is invalid.",
        status_code=422,
    )


def invalid_character_revision_number() -> AppError:
    return AppError(
        code="INVALID_CHARACTER_REVISION_NUMBER",
        message="The Character revision number is invalid.",
        status_code=422,
    )


def character_history_service_unavailable() -> AppError:
    return AppError(
        code="CHARACTER_HISTORY_SERVICE_UNAVAILABLE",
        message="Character revision history is unavailable.",
        status_code=503,
        retryable=True,
    )


def invalid_character_list_request() -> AppError:
    return AppError(
        code="REQUEST_VALIDATION_ERROR",
        message="The Character list request is invalid.",
        status_code=422,
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


def raise_character_http_error(exc: Exception) -> Never:
    """Translate known Character failures and preserve unknown global 500s."""
    if isinstance(exc, InvalidCharacterName):
        mapped = AppError(
            code="INVALID_CHARACTER_NAME",
            message="The Character name is invalid.",
            status_code=422,
            details={"field": "name"},
        )
    elif isinstance(exc, InvalidCharacterRole):
        mapped = AppError(
            code="INVALID_CHARACTER_ROLE",
            message="The Character role is invalid.",
            status_code=422,
            details={"field": "role"},
        )
    elif isinstance(exc, InvalidCharacterProfile):
        mapped = AppError(
            code="INVALID_CHARACTER_PROFILE",
            message="The Character profile is invalid.",
            status_code=422,
            details={"field": "profile"},
        )
    elif isinstance(exc, CharacterRevisionNotFound):
        mapped = AppError(
            code="CHARACTER_REVISION_NOT_FOUND",
            message="The Character revision was not found.",
            status_code=404,
        )
    elif isinstance(exc, CharacterProjectNotFound):
        mapped = AppError(
            code="PROJECT_NOT_FOUND",
            message="The Project was not found.",
            status_code=404,
        )
    elif isinstance(exc, CharacterNotFound):
        mapped = AppError(
            code="CHARACTER_NOT_FOUND",
            message="The Character was not found.",
            status_code=404,
        )
    elif isinstance(exc, CharacterAlreadyExists):
        mapped = AppError(
            code="CHARACTER_ID_CONFLICT",
            message="The Character identifier conflicts with stored data.",
            status_code=409,
        )
    elif isinstance(exc, ConcurrencyConflict):
        mapped = AppError(
            code="CHARACTER_VERSION_CONFLICT",
            message="The Character version does not match the current version.",
            status_code=412,
            details={
                "expected_version": exc.expected_version,
                "actual_version": exc.actual_version,
            },
        )
    elif isinstance(exc, CharacterDataCorruption) and has_database_driver_cause(exc):
        mapped = AppError(
            code="CHARACTER_PERSISTENCE_UNAVAILABLE",
            message="Character persistence is unavailable.",
            status_code=503,
            retryable=True,
        )
    elif isinstance(exc, CharacterDataCorruption):
        mapped = AppError(
            code="CHARACTER_DATA_CORRUPTION",
            message="The stored Character state is unavailable.",
            status_code=500,
        )
    elif isinstance(exc, CharacterRepositoryError):
        mapped = AppError(
            code="CHARACTER_PERSISTENCE_UNAVAILABLE",
            message="Character persistence is unavailable.",
            status_code=503,
            retryable=True,
        )
    elif isinstance(exc, InvalidDomainIdentifier):
        mapped = invalid_character_id()
    else:
        raise exc
    raise mapped from exc


__all__ = [
    "character_command_service_unavailable",
    "character_history_service_unavailable",
    "character_query_service_unavailable",
    "invalid_character_cursor",
    "invalid_character_id",
    "invalid_character_list_request",
    "invalid_character_revision_cursor",
    "invalid_character_revision_history_request",
    "invalid_character_revision_number",
    "invalid_if_match",
    "invalid_project_id",
    "precondition_required",
    "raise_character_http_error",
    "unsupported_media_type",
]

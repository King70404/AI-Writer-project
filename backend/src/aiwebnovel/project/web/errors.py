"""Safe Project-domain and persistence failure mapping for HTTP responses."""

from typing import Never

from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidDomainIdentifier
from aiwebnovel.project.errors import (
    InvalidProjectDescription,
    InvalidProjectTitle,
    ProjectAlreadyExists,
    ProjectDataCorruption,
    ProjectNotFound,
    ProjectRepositoryError,
)


def project_service_unavailable() -> AppError:
    """Build a stable error for an application whose Project services are absent."""
    return AppError(
        code="PROJECT_SERVICE_UNAVAILABLE",
        message="Project service is unavailable.",
        status_code=503,
        retryable=True,
    )


def precondition_required() -> AppError:
    """Build the required If-Match precondition error."""
    return AppError(
        code="PRECONDITION_REQUIRED",
        message="A valid If-Match header is required.",
        status_code=428,
    )


def invalid_if_match() -> AppError:
    """Build the malformed If-Match error without echoing the header."""
    return AppError(
        code="INVALID_IF_MATCH",
        message="The If-Match header is invalid.",
        status_code=400,
    )


def invalid_project_list_cursor() -> AppError:
    """Build the stable malformed cursor error without echoing its value."""
    return AppError(
        code="INVALID_CURSOR",
        message="The Project list cursor is invalid.",
        status_code=400,
    )


def invalid_project_list_request() -> AppError:
    """Build a safe validation error for invalid list query parameters."""
    return AppError(
        code="REQUEST_VALIDATION_ERROR",
        message="请求参数验证失败。",
        status_code=422,
        details={
            "errors": [
                {
                    "field": "query.limit",
                    "type": "validation_error",
                    "message": "Invalid request value.",
                }
            ]
        },
    )


def project_not_found() -> AppError:
    """Build a resource-absence error without exposing the supplied identifier."""
    return AppError(
        code="PROJECT_NOT_FOUND",
        message="The Project was not found.",
        status_code=404,
    )


def raise_project_http_error(exc: Exception) -> Never:
    """Translate only known Project failures; unknown failures remain global 500s."""
    if isinstance(exc, InvalidDomainIdentifier):
        mapped = AppError(
            code="INVALID_PROJECT_ID",
            message="The Project identifier is invalid.",
            status_code=422,
        )
    elif isinstance(exc, InvalidProjectTitle):
        mapped = AppError(
            code="INVALID_PROJECT_TITLE",
            message="The Project title is invalid.",
            status_code=422,
        )
    elif isinstance(exc, InvalidProjectDescription):
        mapped = AppError(
            code="INVALID_PROJECT_DESCRIPTION",
            message="The Project description is invalid.",
            status_code=422,
        )
    elif isinstance(exc, ProjectNotFound):
        mapped = project_not_found()
    elif isinstance(exc, ProjectAlreadyExists):
        mapped = AppError(
            code="PROJECT_ALREADY_EXISTS",
            message="The Project already exists.",
            status_code=409,
        )
    elif isinstance(exc, ConcurrencyConflict):
        mapped = AppError(
            code="PROJECT_VERSION_CONFLICT",
            message="The Project version does not match the current version.",
            status_code=412,
            details={
                "expected_version": exc.expected_version,
                "actual_version": exc.actual_version,
            },
        )
    elif isinstance(exc, ProjectDataCorruption):
        mapped = AppError(
            code="PROJECT_DATA_CORRUPTION",
            message="The stored Project state is unavailable.",
            status_code=500,
        )
    elif isinstance(exc, ProjectRepositoryError):
        mapped = AppError(
            code="PROJECT_PERSISTENCE_UNAVAILABLE",
            message="Project persistence is unavailable.",
            status_code=503,
            retryable=True,
        )
    else:
        raise exc
    raise mapped from exc


__all__ = [
    "invalid_if_match",
    "invalid_project_list_cursor",
    "invalid_project_list_request",
    "precondition_required",
    "project_not_found",
    "project_service_unavailable",
    "raise_project_http_error",
]

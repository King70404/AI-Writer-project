"""FastAPI dependencies for explicitly composed Project application services."""

from fastapi import Request

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.project.application.services import ProjectCommandService, ProjectQueryService
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.web.errors import (
    invalid_if_match,
    precondition_required,
    project_service_unavailable,
    raise_project_http_error,
)
from aiwebnovel.project.web.etags import InvalidProjectIfMatch, parse_project_if_match


def get_project_id(project_id: str) -> str:
    """Validate and canonicalize a Project path identifier before a use case runs."""
    try:
        return str(ProjectId.parse(project_id))
    except InvalidDomainIdentifier as exc:
        raise_project_http_error(exc)


def get_required_project_version(request: Request) -> ConcurrencyVersion:
    """Require exactly one canonical If-Match header before body validation."""
    if_match_values = request.headers.getlist("If-Match")
    if not if_match_values:
        raise precondition_required()
    if len(if_match_values) != 1:
        raise invalid_if_match()
    try:
        return parse_project_if_match(if_match_values[0])
    except InvalidProjectIfMatch as exc:
        raise invalid_if_match() from exc


def get_project_command_service(request: Request) -> ProjectCommandService:
    """Return this application instance's command service or fail safely."""
    service = getattr(request.app.state, "project_command_service", None)
    if not isinstance(service, ProjectCommandService):
        raise project_service_unavailable()
    return service


def get_project_query_service(request: Request) -> ProjectQueryService:
    """Return this application instance's query service or fail safely."""
    service = getattr(request.app.state, "project_query_service", None)
    if not isinstance(service, ProjectQueryService):
        raise project_service_unavailable()
    return service


__all__ = [
    "get_project_command_service",
    "get_project_id",
    "get_project_query_service",
    "get_required_project_version",
]

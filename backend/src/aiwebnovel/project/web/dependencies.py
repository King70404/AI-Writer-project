"""FastAPI dependencies for explicitly composed Project application services."""

from fastapi import Request

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError, InvalidDomainIdentifier
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.application.queries import (
    DEFAULT_PROJECT_LIST_LIMIT,
    DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
    GetProjectRevisionQuery,
    ListProjectRevisionsQuery,
    ListProjectsQuery,
    validate_project_list_limit,
    validate_project_revision_history_limit,
)
from aiwebnovel.project.application.services import (
    ProjectCommandService,
    ProjectListQueryService,
    ProjectQueryService,
    ProjectRevisionHistoryQueryService,
)
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.web.cursors import (
    InvalidProjectListCursor,
    decode_project_list_cursor,
)
from aiwebnovel.project.web.errors import (
    invalid_if_match,
    invalid_project_list_cursor,
    invalid_project_list_request,
    invalid_project_revision_cursor,
    invalid_revision_number,
    precondition_required,
    project_service_unavailable,
    raise_project_http_error,
)
from aiwebnovel.project.web.etags import InvalidProjectIfMatch, parse_project_if_match
from aiwebnovel.project.web.revision_cursors import (
    InvalidProjectRevisionCursor,
    decode_project_revision_cursor,
)


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


def get_project_list_query(request: Request) -> ListProjectsQuery:
    """Validate limit before strictly decoding the optional opaque cursor."""
    if any(key not in {"limit", "cursor"} for key in request.query_params):
        raise invalid_project_list_request()
    limit_values = request.query_params.getlist("limit")
    if len(limit_values) > 1:
        raise invalid_project_list_request()
    if limit_values:
        raw_limit = limit_values[0]
        if not raw_limit or not raw_limit.isascii() or not raw_limit.isdecimal():
            raise invalid_project_list_request()
        try:
            limit = validate_project_list_limit(int(raw_limit, 10))
        except (ValueError, OverflowError):
            raise invalid_project_list_request() from None
    else:
        limit = DEFAULT_PROJECT_LIST_LIMIT

    cursor_values = request.query_params.getlist("cursor")
    if len(cursor_values) > 1:
        raise invalid_project_list_cursor()
    if cursor_values:
        try:
            after = decode_project_list_cursor(cursor_values[0])
        except InvalidProjectListCursor as exc:
            raise invalid_project_list_cursor() from exc
    else:
        after = None
    return ListProjectsQuery(limit=limit, after=after)


def get_project_list_query_service(request: Request) -> ProjectListQueryService:
    """Return this application instance's list service or fail safely."""
    service = getattr(request.app.state, "project_list_query_service", None)
    if not isinstance(service, ProjectListQueryService):
        raise project_service_unavailable()
    return service


def get_project_revision_history_query(
    request: Request,
    project_id: str,
) -> ListProjectRevisionsQuery:
    """Validate Project, limit, then bind the optional history cursor."""
    canonical_project_id = get_project_id(project_id)
    if any(key not in {"limit", "cursor"} for key in request.query_params):
        raise invalid_project_list_request()
    limit_values = request.query_params.getlist("limit")
    if len(limit_values) > 1:
        raise invalid_project_list_request()
    if limit_values:
        raw_limit = limit_values[0]
        if not raw_limit or not raw_limit.isascii() or not raw_limit.isdecimal():
            raise invalid_project_list_request()
        try:
            limit = validate_project_revision_history_limit(int(raw_limit, 10))
        except (ValueError, OverflowError):
            raise invalid_project_list_request() from None
    else:
        limit = DEFAULT_PROJECT_REVISION_HISTORY_LIMIT

    cursor_values = request.query_params.getlist("cursor")
    if len(cursor_values) > 1:
        raise invalid_project_revision_cursor()
    if cursor_values:
        try:
            after = decode_project_revision_cursor(
                cursor_values[0],
                project_id=canonical_project_id,
            )
        except InvalidProjectRevisionCursor as exc:
            raise invalid_project_revision_cursor() from exc
    else:
        after = None
    return ListProjectRevisionsQuery(
        project_id=canonical_project_id,
        limit=limit,
        after=after,
    )


def get_project_revision_query(
    project_id: str,
    revision_number: str,
) -> GetProjectRevisionQuery:
    """Validate Project ID then parse one canonical positive decimal revision."""
    canonical_project_id = get_project_id(project_id)
    if (
        not revision_number
        or not revision_number.isascii()
        or not revision_number.isdecimal()
        or revision_number.startswith("0")
    ):
        raise invalid_revision_number()
    try:
        parsed_revision = RevisionNumber(int(revision_number, 10))
    except (DomainError, TypeError, ValueError, OverflowError):
        raise invalid_revision_number() from None
    if str(int(parsed_revision)) != revision_number:
        raise invalid_revision_number()
    return GetProjectRevisionQuery(
        project_id=canonical_project_id,
        revision_number=int(parsed_revision),
    )


def get_project_revision_history_query_service(
    request: Request,
) -> ProjectRevisionHistoryQueryService:
    """Return this application's history service or fail safely."""
    service = getattr(request.app.state, "project_revision_history_query_service", None)
    if not isinstance(service, ProjectRevisionHistoryQueryService):
        raise project_service_unavailable()
    return service


__all__ = [
    "get_project_command_service",
    "get_project_id",
    "get_project_list_query",
    "get_project_list_query_service",
    "get_project_query_service",
    "get_project_revision_history_query",
    "get_project_revision_history_query_service",
    "get_project_revision_query",
    "get_required_project_version",
]

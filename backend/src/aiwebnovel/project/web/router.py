"""The intentionally bounded Project HTTP endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.application.commands import (
    CreateProjectCommand,
    DeleteProjectCommand,
    ReviseProjectCommand,
)
from aiwebnovel.project.application.queries import (
    DEFAULT_PROJECT_LIST_LIMIT,
    DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
    MAX_PROJECT_LIST_LIMIT,
    MAX_PROJECT_REVISION_HISTORY_LIMIT,
    GetProjectQuery,
    GetProjectRevisionQuery,
    ListProjectRevisionsQuery,
    ListProjectsQuery,
)
from aiwebnovel.project.application.services import (
    ProjectCommandService,
    ProjectListQueryService,
    ProjectQueryService,
    ProjectRevisionHistoryQueryService,
)
from aiwebnovel.project.errors import ProjectRevisionNotFound
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.web.dependencies import (
    get_project_command_service,
    get_project_id,
    get_project_list_query,
    get_project_list_query_service,
    get_project_query_service,
    get_project_revision_history_query,
    get_project_revision_history_query_service,
    get_project_revision_query,
    get_required_project_version,
)
from aiwebnovel.project.web.dto import (
    CreateProjectRequest,
    DeleteProjectResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectRevisionHistoryResponse,
    ProjectRevisionResponse,
    ReviseProjectRequest,
)
from aiwebnovel.project.web.errors import (
    project_not_found,
    raise_project_http_error,
)
from aiwebnovel.project.web.etags import format_project_etag
from aiwebnovel.project.web.mappers import (
    project_list_response_from_page,
    project_response_from_snapshot,
    project_revision_history_response_from_page,
    project_revision_response_from_snapshot,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Malformed If-Match header."},
    404: {"description": "Project not found."},
    412: {"description": "The supplied version is stale."},
    422: {"description": "The request or a Project value is invalid."},
    428: {"description": "If-Match is required."},
    503: {"description": "Project persistence or service is unavailable."},
}

_LIST_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "The opaque keyset cursor is invalid."},
    422: {"description": "The list query parameters are invalid."},
    500: {"description": "Stored Project list data is inconsistent."},
    503: {"description": "Project persistence or service is unavailable."},
}

_REVISION_HISTORY_LIST_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "The Project-bound revision keyset cursor is invalid."},
    404: {"description": "Project not found."},
    422: {"description": "The Project identifier or list limit is invalid."},
    500: {"description": "Stored Project revision data is inconsistent."},
    503: {"description": "Project persistence or service is unavailable."},
}

_REVISION_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "Project or immutable revision not found."},
    422: {"description": "The Project identifier or revision number is invalid."},
    500: {"description": "Stored Project revision data is inconsistent."},
    503: {"description": "Project persistence or service is unavailable."},
}


def _set_project_headers(response: Response, project: ProjectResponse) -> None:
    response.headers["ETag"] = format_project_etag(project.concurrency_version)
    response.headers["Cache-Control"] = "no-store"


def create_project_router(*, api_prefix: str) -> APIRouter:
    """Create the versioned Project router without touching persistence."""
    router = APIRouter(prefix=f"{api_prefix}/projects", tags=["Projects"])

    @router.get(
        "",
        response_model=ProjectListResponse,
        responses=_LIST_ERROR_RESPONSES,
        summary="List current Projects",
        description=(
            "Returns current-revision summaries ordered by immutable created_at DESC and "
            "project_id DESC using keyset pagination. The opaque cursor is a transport token, "
            "not a security credential. Description and total count are intentionally omitted; "
            "search, filtering, and custom sorting are not supported. Logically deleted Projects "
            "are omitted from ordinary author use."
        ),
        openapi_extra={
            "parameters": [
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "description": "Page size from 1 through 100; defaults to 20.",
                    "schema": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_PROJECT_LIST_LIMIT,
                        "default": DEFAULT_PROJECT_LIST_LIMIT,
                    },
                },
                {
                    "name": "cursor",
                    "in": "query",
                    "required": False,
                    "description": "Opaque untrusted keyset cursor returned by the prior page.",
                    "schema": {"type": "string", "nullable": True},
                },
            ]
        },
    )
    def list_projects(
        response: Response,
        query: Annotated[ListProjectsQuery, Depends(get_project_list_query)],
        service: Annotated[
            ProjectListQueryService,
            Depends(get_project_list_query_service),
        ],
    ) -> ProjectListResponse:
        try:
            page = service.list_projects(query)
        except DomainError as exc:
            raise_project_http_error(exc)
        result = project_list_response_from_page(page)
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.post(
        "",
        response_model=ProjectResponse,
        status_code=status.HTTP_201_CREATED,
        responses={422: _ERROR_RESPONSES[422], 503: _ERROR_RESPONSES[503]},
        summary="Create a Project",
        description=(
            "Creates a Project and its initial revision. The strong ETag represents "
            "ConcurrencyVersion. Immutable history is exposed separately as read-only data."
        ),
    )
    def create_project(
        request: CreateProjectRequest,
        response: Response,
        service: Annotated[ProjectCommandService, Depends(get_project_command_service)],
    ) -> ProjectResponse:
        try:
            snapshot = service.create_project(
                CreateProjectCommand(title=request.title, description=request.description)
            )
        except DomainError as exc:
            raise_project_http_error(exc)
        project = project_response_from_snapshot(snapshot)
        _set_project_headers(response, project)
        response.headers["Location"] = f"{api_prefix}/projects/{project.project_id}"
        return project

    @router.get(
        "/{project_id}/revisions",
        response_model=ProjectRevisionHistoryResponse,
        responses=_REVISION_HISTORY_LIST_ERROR_RESPONSES,
        summary="List immutable Project revisions",
        description=(
            "Returns immutable revision summaries in RevisionNumber DESC order with a "
            "Project-bound keyset cursor. List items omit description and no total count is "
            "computed. The cursor is not a security credential or cross-request snapshot. "
            "Historical revisions cannot be edited, restored, or rolled back."
        ),
        openapi_extra={
            "parameters": [
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "description": "Page size from 1 through 100; defaults to 20.",
                    "schema": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_PROJECT_REVISION_HISTORY_LIMIT,
                        "default": DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
                    },
                },
                {
                    "name": "cursor",
                    "in": "query",
                    "required": False,
                    "description": ("Opaque keyset cursor bound to the Project in this path."),
                    "schema": {"type": "string", "nullable": True},
                },
            ]
        },
    )
    def list_project_revisions(
        response: Response,
        query: Annotated[
            ListProjectRevisionsQuery,
            Depends(get_project_revision_history_query),
        ],
        service: Annotated[
            ProjectRevisionHistoryQueryService,
            Depends(get_project_revision_history_query_service),
        ],
    ) -> ProjectRevisionHistoryResponse:
        try:
            page = service.list_revisions(query)
        except DomainError as exc:
            raise_project_http_error(exc)
        result = project_revision_history_response_from_page(page)
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.get(
        "/{project_id}/revisions/{revision_number}",
        response_model=ProjectRevisionResponse,
        responses=_REVISION_ERROR_RESPONSES,
        summary="Get one immutable Project revision",
        description=(
            "Returns the original read-only title and description for one canonical positive "
            "RevisionNumber. Historical content cannot be edited, restored, or rolled back."
        ),
    )
    def get_project_revision(
        response: Response,
        query: Annotated[
            GetProjectRevisionQuery,
            Depends(get_project_revision_query),
        ],
        service: Annotated[
            ProjectRevisionHistoryQueryService,
            Depends(get_project_revision_history_query_service),
        ],
    ) -> ProjectRevisionResponse:
        try:
            snapshot = service.get_revision(query)
            if snapshot is None:
                raise ProjectRevisionNotFound(
                    ProjectId.parse(query.project_id),
                    RevisionNumber(query.revision_number),
                )
        except DomainError as exc:
            raise_project_http_error(exc)
        result = project_revision_response_from_snapshot(snapshot)
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.get(
        "/{project_id}",
        response_model=ProjectResponse,
        responses={
            404: _ERROR_RESPONSES[404],
            422: _ERROR_RESPONSES[422],
            503: _ERROR_RESPONSES[503],
        },
        summary="Get the current Project",
        description=(
            "Returns only the current Project snapshot. The strong ETag represents "
            "ConcurrencyVersion; revision history is not exposed."
        ),
    )
    def get_project(
        response: Response,
        project_id: Annotated[str, Depends(get_project_id)],
        service: Annotated[ProjectQueryService, Depends(get_project_query_service)],
    ) -> ProjectResponse:
        try:
            snapshot = service.get_project(GetProjectQuery(project_id=project_id))
        except DomainError as exc:
            raise_project_http_error(exc)
        if snapshot is None:
            raise project_not_found()
        project = project_response_from_snapshot(snapshot)
        _set_project_headers(response, project)
        return project

    @router.put(
        "/{project_id}",
        response_model=ProjectResponse,
        responses=_ERROR_RESPONSES,
        summary="Completely revise a Project",
        description=(
            "Completely replaces title and description; PATCH is intentionally unsupported. "
            "If-Match must contain the strong ETag whose value is ConcurrencyVersion."
        ),
        openapi_extra={
            "parameters": [
                {
                    "name": "If-Match",
                    "in": "header",
                    "required": True,
                    "description": 'Required strong Project ETag, for example "1".',
                    "schema": {"type": "string"},
                }
            ]
        },
    )
    def revise_project(
        response: Response,
        project_id: Annotated[str, Depends(get_project_id)],
        expected_version: Annotated[
            ConcurrencyVersion,
            Depends(get_required_project_version),
        ],
        service: Annotated[ProjectCommandService, Depends(get_project_command_service)],
        payload: ReviseProjectRequest,
    ) -> ProjectResponse:
        try:
            snapshot = service.revise_project(
                ReviseProjectCommand(
                    project_id=project_id,
                    expected_version=int(expected_version),
                    title=payload.title,
                    description=payload.description,
                )
            )
        except DomainError as exc:
            raise_project_http_error(exc)
        project = project_response_from_snapshot(snapshot)
        _set_project_headers(response, project)
        return project

    @router.post(
        "/{project_id}/delete",
        response_model=DeleteProjectResponse,
        responses=_ERROR_RESPONSES,
        summary="Logically delete a Project",
        description=(
            "Appends an internal immutable tombstone revision so the Project disappears from "
            "ordinary author workflows without rewriting accepted revision history. If-Match "
            "must contain the current strong Project ETag."
        ),
        openapi_extra={
            "parameters": [
                {
                    "name": "If-Match",
                    "in": "header",
                    "required": True,
                    "description": 'Required strong Project ETag, for example "1".',
                    "schema": {"type": "string"},
                }
            ]
        },
    )
    def delete_project(
        project_id: Annotated[str, Depends(get_project_id)],
        expected_version: Annotated[
            ConcurrencyVersion,
            Depends(get_required_project_version),
        ],
        service: Annotated[ProjectCommandService, Depends(get_project_command_service)],
    ) -> DeleteProjectResponse:
        try:
            service.delete_project(
                DeleteProjectCommand(
                    project_id=project_id,
                    expected_version=int(expected_version),
                )
            )
        except DomainError as exc:
            raise_project_http_error(exc)
        return DeleteProjectResponse(deleted=True)

    return router


__all__ = ["create_project_router"]

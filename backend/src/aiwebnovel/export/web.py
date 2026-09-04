"""One plain-text download endpoint composed from existing read services."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.export.application import ExportProjectManuscript
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.novel_structure.web.dependencies import get_query_service
from aiwebnovel.novel_structure.web.errors import raise_novel_structure_http_error
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.errors import ProjectDomainError
from aiwebnovel.project.web.dependencies import get_project_id, get_project_query_service
from aiwebnovel.project.web.errors import raise_project_http_error


def create_export_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix, tags=["Novel Export"])

    @router.get(
        "/projects/{project_id}/export.txt",
        response_class=PlainTextResponse,
        summary="Export the current saved novel as UTF-8 text",
    )
    def export_project_manuscript(
        project_id: Annotated[str, Depends(get_project_id)],
        projects: Annotated[ProjectQueryService, Depends(get_project_query_service)],
        structure: Annotated[NovelStructureQueryService, Depends(get_query_service)],
    ) -> PlainTextResponse:
        try:
            text = ExportProjectManuscript(projects, structure).execute(project_id)
        except ProjectDomainError as exc:
            raise_project_http_error(exc)
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="chapter")
        return PlainTextResponse(
            text,
            headers={
                "Content-Disposition": 'attachment; filename="novel.txt"',
                "Cache-Control": "no-store",
            },
        )

    return router

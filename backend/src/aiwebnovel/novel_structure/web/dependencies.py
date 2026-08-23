"""FastAPI dependencies for composed novel-structure application services."""

from fastapi import Request

from aiwebnovel.api.etags import InvalidIfMatch, parse_strong_if_match
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.novel_structure.application.services import (
    NovelStructureCommandService,
    NovelStructureQueryService,
)
from aiwebnovel.novel_structure.identifiers import ChapterId, OutlineId, VolumeId
from aiwebnovel.novel_structure.web.errors import (
    command_service_unavailable,
    invalid_chapter_id,
    invalid_if_match,
    invalid_outline_id,
    invalid_project_id,
    invalid_volume_id,
    precondition_required,
    query_service_unavailable,
    unsupported_media_type,
)
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.security.request_limits import is_json_media_type


def get_project_id(project_id: str) -> str:
    try:
        return str(ProjectId.parse(project_id))
    except InvalidDomainIdentifier as exc:
        raise invalid_project_id() from exc


def get_outline_id(outline_id: str) -> str:
    try:
        return str(OutlineId.parse(outline_id))
    except InvalidDomainIdentifier as exc:
        raise invalid_outline_id() from exc


def get_volume_id(volume_id: str) -> str:
    try:
        return str(VolumeId.parse(volume_id))
    except InvalidDomainIdentifier as exc:
        raise invalid_volume_id() from exc


def get_chapter_id(chapter_id: str) -> str:
    try:
        return str(ChapterId.parse(chapter_id))
    except InvalidDomainIdentifier as exc:
        raise invalid_chapter_id() from exc


def get_required_version(request: Request) -> ConcurrencyVersion:
    values = request.headers.getlist("If-Match")
    if not values:
        raise precondition_required()
    if len(values) != 1:
        raise invalid_if_match()
    try:
        return parse_strong_if_match(values[0])
    except InvalidIfMatch as exc:
        raise invalid_if_match() from exc


def require_json(request: Request) -> None:
    values = request.headers.getlist("Content-Type")
    if len(values) != 1:
        raise unsupported_media_type()
    try:
        encoded = values[0].encode("ascii")
    except UnicodeEncodeError:
        raise unsupported_media_type() from None
    if not is_json_media_type(encoded):
        raise unsupported_media_type()
    parameters = [part.strip().lower() for part in values[0].split(";")[1:]]
    if any(parameter != "charset=utf-8" for parameter in parameters):
        raise unsupported_media_type()


def get_command_service(request: Request) -> NovelStructureCommandService:
    service = getattr(request.app.state, "novel_structure_command_service", None)
    if not isinstance(service, NovelStructureCommandService):
        raise command_service_unavailable()
    return service


def get_query_service(request: Request) -> NovelStructureQueryService:
    service = getattr(request.app.state, "novel_structure_query_service", None)
    if not isinstance(service, NovelStructureQueryService):
        raise query_service_unavailable()
    return service


__all__ = [
    "get_chapter_id",
    "get_command_service",
    "get_outline_id",
    "get_project_id",
    "get_query_service",
    "get_required_version",
    "get_volume_id",
    "require_json",
]

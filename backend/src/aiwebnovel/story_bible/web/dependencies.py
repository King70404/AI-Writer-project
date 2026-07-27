"""FastAPI dependencies for composed Story Bible application services."""

from fastapi import Request

from aiwebnovel.api.etags import InvalidIfMatch, parse_strong_if_match
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.security.request_limits import is_json_media_type
from aiwebnovel.story_bible.application.services import (
    StoryBibleCommandService,
    StoryBibleQueryService,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId
from aiwebnovel.story_bible.web.errors import (
    invalid_if_match,
    invalid_project_id,
    invalid_story_bible_id,
    precondition_required,
    story_bible_service_unavailable,
    unsupported_media_type,
)


def get_story_bible_project_id(project_id: str) -> str:
    """Validate and canonicalize a nested Project path identifier."""
    try:
        return str(ProjectId.parse(project_id))
    except InvalidDomainIdentifier as exc:
        raise invalid_project_id() from exc


def get_story_bible_id(story_bible_id: str) -> str:
    """Validate and canonicalize a Story Bible path identifier."""
    try:
        return str(StoryBibleId.parse(story_bible_id))
    except InvalidDomainIdentifier as exc:
        raise invalid_story_bible_id() from exc


def get_required_story_bible_version(request: Request) -> ConcurrencyVersion:
    """Require exactly one canonical shared strong If-Match value."""
    values = request.headers.getlist("If-Match")
    if not values:
        raise precondition_required()
    if len(values) != 1:
        raise invalid_if_match()
    try:
        return parse_strong_if_match(values[0])
    except InvalidIfMatch as exc:
        raise invalid_if_match() from exc


def require_story_bible_json(request: Request) -> None:
    """Require one JSON Content-Type with no charset other than UTF-8."""
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


def get_story_bible_command_service(request: Request) -> StoryBibleCommandService:
    """Return this application instance's command service or fail safely."""
    service = getattr(request.app.state, "story_bible_command_service", None)
    if not isinstance(service, StoryBibleCommandService):
        raise story_bible_service_unavailable()
    return service


def get_story_bible_query_service(request: Request) -> StoryBibleQueryService:
    """Return this application instance's query service or fail safely."""
    service = getattr(request.app.state, "story_bible_query_service", None)
    if not isinstance(service, StoryBibleQueryService):
        raise story_bible_service_unavailable()
    return service


__all__ = [
    "get_required_story_bible_version",
    "get_story_bible_command_service",
    "get_story_bible_id",
    "get_story_bible_project_id",
    "get_story_bible_query_service",
    "require_story_bible_json",
]

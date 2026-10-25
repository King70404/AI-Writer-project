"""Novel-structure HTTP DTO, route, ETag, and ownership contracts."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from tests.backend.ai_workflow_contract_support import (
    AI_WORKFLOW_OPERATIONS,
    BACKUP_OPERATIONS,
    CANDIDATE_BUDGET_OPERATIONS,
    STORY_CONTROL_OPERATIONS,
    STORY_MEMORY_OPERATIONS,
    USAGE_OPERATIONS,
    WORKBENCH_OPERATIONS,
    WRITING_PREPARATION_OPERATIONS,
)
from tests.backend.character_http_support import issue_write_headers
from tests.backend.factories import create_test_app
from tests.backend.novel_structure_repository_support import (
    chapter_id,
    chapter_revision_id,
    outline_id,
    outline_revision_id,
    project_id,
    volume_id,
    volume_revision_id,
)

from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidDomainIdentifier
from aiwebnovel.novel_structure.application.models import (
    ChapterContentSnapshot,
    ChapterSnapshot,
    OutlineSnapshot,
    VolumeSnapshot,
)
from aiwebnovel.novel_structure.application.queries import GetVolumeQuery
from aiwebnovel.novel_structure.errors import (
    ChapterAlreadyExists,
    ChapterNotFound,
    ChapterPositionConflict,
    ChapterVolumeOwnershipMismatch,
    InvalidManuscriptContent,
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
from aiwebnovel.novel_structure.web import dto as dto_module
from aiwebnovel.novel_structure.web.dependencies import (
    get_chapter_id,
    get_command_service,
    get_outline_id,
    get_project_id,
    get_query_service,
    get_required_version,
    get_volume_id,
    require_json,
)
from aiwebnovel.novel_structure.web.dto import (
    ChapterContentResponse,
    ChapterResponse,
    CreateChapterRequest,
    CreateOutlineRequest,
    CreateVolumeRequest,
    OutlineResponse,
    UpdateChapterContentRequest,
    UpdateChapterRequest,
    UpdateOutlineRequest,
    UpdateVolumeRequest,
    VolumeResponse,
)
from aiwebnovel.novel_structure.web.errors import raise_novel_structure_http_error
from aiwebnovel.novel_structure.web.mappers import (
    chapter_content_response,
    chapter_response,
    create_chapter_command,
    create_outline_command,
    create_volume_command,
    outline_response,
    update_chapter_command,
    update_chapter_content_command,
    update_outline_command,
    update_volume_command,
    volume_response,
)
from aiwebnovel.project.errors import ProjectNotFound

pytestmark = pytest.mark.unit

BASE_TIME = datetime(2026, 8, 15, 1, 2, 3, tzinfo=UTC)
PROJECT_ID = str(project_id(1))
SECOND_PROJECT_ID = str(project_id(2))
OUTLINE_ID = str(outline_id(10))
VOLUME_ID = str(volume_id(20))
CHAPTER_ID = str(chapter_id(30))


def outline_snapshot(*, version: int = 1) -> OutlineSnapshot:
    updated = BASE_TIME + timedelta(seconds=version - 1)
    return OutlineSnapshot(
        outline_id=OUTLINE_ID,
        project_id=PROJECT_ID,
        current_revision_id=str(outline_revision_id(100 + version)),
        revision_number=version,
        concurrency_version=version,
        title=f"Outline {version}",
        summary=f"Summary {version}",
        created_at=BASE_TIME,
        updated_at=updated,
        revision_created_at=updated,
    )


def volume_snapshot(*, version: int = 1, owner: str = PROJECT_ID) -> VolumeSnapshot:
    updated = BASE_TIME + timedelta(seconds=version - 1)
    return VolumeSnapshot(
        volume_id=VOLUME_ID,
        project_id=owner,
        current_revision_id=str(volume_revision_id(200 + version)),
        revision_number=version,
        concurrency_version=version,
        title=f"Volume {version}",
        summary=f"Summary {version}",
        position=version,
        created_at=BASE_TIME,
        updated_at=updated,
        revision_created_at=updated,
    )


def chapter_snapshot(*, version: int = 1) -> ChapterSnapshot:
    updated = BASE_TIME + timedelta(seconds=version - 1)
    return ChapterSnapshot(
        chapter_id=CHAPTER_ID,
        project_id=PROJECT_ID,
        volume_id=VOLUME_ID,
        current_revision_id=str(chapter_revision_id(300 + version)),
        revision_number=version,
        concurrency_version=version,
        title=f"Chapter {version}",
        summary=f"Summary {version}",
        position=version,
        created_at=BASE_TIME,
        updated_at=updated,
        revision_created_at=updated,
    )


def chapter_content_snapshot(*, version: int = 1) -> ChapterContentSnapshot:
    updated = BASE_TIME + timedelta(seconds=version - 1)
    return ChapterContentSnapshot(
        chapter_id=CHAPTER_ID,
        project_id=PROJECT_ID,
        volume_id=VOLUME_ID,
        current_revision_id=str(chapter_revision_id(300 + version)),
        revision_number=version,
        concurrency_version=version,
        content=f"Draft {version}",
        updated_at=updated,
        revision_created_at=updated,
    )


class _CommandSpy:
    def create_outline(self, command):  # type: ignore[no-untyped-def]
        self.last = command
        return outline_snapshot()

    def update_outline(self, command):  # type: ignore[no-untyped-def]
        self.last = command
        return outline_snapshot(version=2)

    def create_volume(self, command):  # type: ignore[no-untyped-def]
        self.last = command
        return volume_snapshot()

    def update_volume(self, command):  # type: ignore[no-untyped-def]
        self.last = command
        return volume_snapshot(version=2)

    def create_chapter(self, command):  # type: ignore[no-untyped-def]
        self.last = command
        return chapter_snapshot()

    def update_chapter(self, command):  # type: ignore[no-untyped-def]
        self.last = command
        return chapter_snapshot(version=2)

    def update_chapter_content(self, command):  # type: ignore[no-untyped-def]
        self.last = command
        return chapter_content_snapshot(version=2)


class _QuerySpy:
    def __init__(self, *, owner: str = PROJECT_ID) -> None:
        self.owner = owner
        self.list_chapter_calls = 0

    def get_outline_for_project(self, query):  # type: ignore[no-untyped-def]
        self.last = query
        return outline_snapshot()

    def list_volumes(self, query):  # type: ignore[no-untyped-def]
        self.last = query
        return (volume_snapshot(),)

    def get_volume(self, query):  # type: ignore[no-untyped-def]
        assert type(query) is GetVolumeQuery
        self.last = query
        return volume_snapshot(owner=self.owner)

    def list_chapters(self, query):  # type: ignore[no-untyped-def]
        self.list_chapter_calls += 1
        self.last = query
        return (chapter_snapshot(),)

    def get_chapter(self, query):  # type: ignore[no-untyped-def]
        self.last = query
        return chapter_snapshot()

    def get_chapter_content(self, query):  # type: ignore[no-untyped-def]
        self.last = query
        return chapter_content_snapshot()


def _app(tmp_path: Path, command: object, query: object):  # type: ignore[no-untyped-def]
    app = create_test_app(data_root=(tmp_path / "novel-structure-http").resolve())
    app.dependency_overrides[get_command_service] = lambda: command
    app.dependency_overrides[get_query_service] = lambda: query
    return app


def _request(*headers: tuple[bytes, bytes], app: FastAPI | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": list(headers),
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 1),
            "root_path": "",
            "app": app or FastAPI(),
        }
    )


def test_strict_requests_and_explicit_mappers() -> None:
    create_outline = CreateOutlineRequest(title="Outline", summary="Summary")
    create_volume = CreateVolumeRequest(title="Volume", summary="Summary", position=1)
    create_chapter = CreateChapterRequest(title="Chapter", summary="Summary", position=1)
    revise_outline = UpdateOutlineRequest(title="Outline 2", summary="Summary 2")
    revise_volume = UpdateVolumeRequest(title="Volume 2", summary="Summary 2", position=2)
    revise_chapter = UpdateChapterRequest(title="Chapter 2", summary="Summary 2", position=2)
    revise_content = UpdateChapterContentRequest(content="Draft")

    assert create_outline_command(PROJECT_ID, create_outline).project_id == PROJECT_ID
    assert create_volume_command(PROJECT_ID, create_volume).position == 1
    assert create_chapter_command(PROJECT_ID, VOLUME_ID, create_chapter).volume_id == VOLUME_ID
    assert update_outline_command(OUTLINE_ID, 1, revise_outline).expected_version == 1
    assert update_volume_command(VOLUME_ID, 1, revise_volume).position == 2
    assert update_chapter_command(CHAPTER_ID, 1, revise_chapter).position == 2
    assert update_chapter_content_command(CHAPTER_ID, 1, revise_content).content == "Draft"
    assert outline_response(outline_snapshot()).model_dump()["outline_id"] == OUTLINE_ID
    assert volume_response(volume_snapshot()).model_dump()["volume_id"] == VOLUME_ID
    assert chapter_response(chapter_snapshot()).model_dump()["chapter_id"] == CHAPTER_ID
    assert chapter_content_response(chapter_content_snapshot()).model_dump()["content"] == "Draft 1"

    with pytest.raises(ValidationError):
        CreateOutlineRequest(title="Outline", summary="Summary", extra="no")
    with pytest.raises(ValidationError):
        CreateVolumeRequest(title="Volume", summary="Summary", position=True)
    with pytest.raises(ValidationError):
        UpdateChapterRequest(title=1, summary="Summary", position=1)
    with pytest.raises(ValidationError):
        UpdateChapterContentRequest(content="Draft", extra="no")
    with pytest.raises(ValidationError):
        OutlineResponse(
            **{**outline_response(outline_snapshot()).model_dump(), "outline_id": "bad"}
        )


@pytest.mark.parametrize(
    "mutations",
    [
        {"project_id": "bad"},
        {"current_revision_id": "bad"},
        {"revision_number": 0},
        {"concurrency_version": 0},
        {"title": "x" * 121},
        {"summary": "x" * 2_001},
        {"title": "  not canonical  "},
        {"summary": "not\r\ncanonical"},
        {"created_at": datetime(2026, 8, 15)},
        {"created_at": datetime(2026, 8, 15, tzinfo=timezone(timedelta(hours=8)))},
        {"revision_created_at": BASE_TIME + timedelta(seconds=1)},
    ],
)
def test_response_dto_rejects_each_invalid_boundary(mutations: dict[str, object]) -> None:
    values = outline_response(outline_snapshot()).model_dump()
    values.update(mutations)
    with pytest.raises(ValidationError):
        OutlineResponse(**values)


@pytest.mark.parametrize(
    "mutations",
    [
        {"content": "secret\x00"},
        {"content": "not\r\ncanonical"},
        {"concurrency_version": 2},
        {"revision_created_at": BASE_TIME + timedelta(seconds=1)},
    ],
)
def test_chapter_content_response_rejects_invalid_or_noncanonical_state(
    mutations: dict[str, object],
) -> None:
    values = chapter_content_response(chapter_content_snapshot()).model_dump()
    values.update(mutations)
    with pytest.raises(ValidationError) as caught:
        ChapterContentResponse(**values)
    assert "secret" not in str(caught.value)


def test_dto_canonical_guard_rejects_normalizing_parser() -> None:
    with pytest.raises(ValueError, match="canonical"):
        dto_module._canonical("raw", lambda _: "normalized", "field")


@pytest.mark.parametrize(
    ("call", "arguments"),
    [
        (create_outline_command, (1, CreateOutlineRequest(title="A", summary=""))),
        (update_outline_command, (OUTLINE_ID, True, UpdateOutlineRequest(title="A", summary=""))),
        (create_volume_command, (PROJECT_ID, object())),
        (
            update_volume_command,
            (VOLUME_ID, 1, object()),
        ),
        (create_chapter_command, (PROJECT_ID, VOLUME_ID, object())),
        (update_chapter_command, (CHAPTER_ID, 1, object())),
        (update_chapter_content_command, (CHAPTER_ID, 1, object())),
        (outline_response, (object(),)),
        (volume_response, (object(),)),
        (chapter_response, (object(),)),
        (chapter_content_response, (object(),)),
    ],
)
def test_mappers_reject_wrong_exact_types(call, arguments) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(TypeError):
        call(*arguments)


def test_identifier_header_json_and_service_dependencies_are_strict() -> None:
    assert get_outline_id(OUTLINE_ID) == OUTLINE_ID
    assert get_volume_id(VOLUME_ID) == VOLUME_ID
    assert get_chapter_id(CHAPTER_ID) == CHAPTER_ID
    for dependency in (get_outline_id, get_volume_id, get_chapter_id):
        with pytest.raises(AppError) as raised:
            dependency("bad")
        assert raised.value.status_code == 422

    assert int(get_required_version(_request((b"if-match", b'"7"')))) == 7
    for request in (
        _request(),
        _request((b"if-match", b'"1"'), (b"if-match", b'"2"')),
        _request((b"if-match", b'W/"1"')),
    ):
        with pytest.raises(AppError):
            get_required_version(request)

    require_json(_request((b"content-type", b"application/json")))
    require_json(_request((b"content-type", b"application/json; charset=utf-8")))
    for request in (
        _request(),
        _request((b"content-type", b"application/json"), (b"content-type", b"application/json")),
        _request((b"content-type", "application/json; note=中".encode())),
        _request((b"content-type", b"text/plain")),
        _request((b"content-type", b"application/json; charset=latin1")),
    ):
        with pytest.raises(AppError) as raised:
            require_json(request)
        assert raised.value.status_code == 415

    app = FastAPI()
    with pytest.raises(AppError):
        get_command_service(_request(app=app))
    with pytest.raises(AppError):
        get_query_service(_request(app=app))

    from aiwebnovel.novel_structure.application.services import (
        NovelStructureCommandService,
        NovelStructureQueryService,
    )

    command = NovelStructureCommandService(
        object(),
        object(),
        lambda: BASE_TIME,
        *([lambda: object()] * 6),  # type: ignore[arg-type]
    )
    query = NovelStructureQueryService(object(), object())  # type: ignore[arg-type]
    app.state.novel_structure_command_service = command
    app.state.novel_structure_query_service = query
    assert get_command_service(_request(app=app)) is command
    assert get_query_service(_request(app=app)) is query
    with pytest.raises(ValidationError):
        VolumeResponse(**{**volume_response(volume_snapshot()).model_dump(), "position": 0})
    with pytest.raises(ValidationError):
        ChapterResponse(
            **{
                **chapter_response(chapter_snapshot()).model_dump(),
                "concurrency_version": 2,
            }
        )


def test_all_eleven_routes_return_bounded_current_resources(tmp_path: Path) -> None:
    command = _CommandSpy()
    query = _QuerySpy()
    with TestClient(_app(tmp_path, command, query)) as client:
        headers = issue_write_headers(client)
        outline_create = client.post(
            f"/api/v1/projects/{PROJECT_ID}/outline",
            headers=headers,
            json={"title": "Outline", "summary": "Summary"},
        )
        outline_read = client.get(f"/api/v1/projects/{PROJECT_ID}/outline")
        outline_update = client.put(
            f"/api/v1/outlines/{OUTLINE_ID}",
            headers={**headers, "If-Match": '"1"'},
            json={"title": "Outline 2", "summary": "Summary 2"},
        )
        volume_create = client.post(
            f"/api/v1/projects/{PROJECT_ID}/volumes",
            headers=headers,
            json={"title": "Volume", "summary": "Summary", "position": 1},
        )
        volume_list = client.get(f"/api/v1/projects/{PROJECT_ID}/volumes")
        volume_read = client.get(f"/api/v1/volumes/{VOLUME_ID}")
        volume_update = client.put(
            f"/api/v1/volumes/{VOLUME_ID}",
            headers={**headers, "If-Match": '"1"'},
            json={"title": "Volume 2", "summary": "Summary 2", "position": 2},
        )
        chapter_create = client.post(
            f"/api/v1/projects/{PROJECT_ID}/volumes/{VOLUME_ID}/chapters",
            headers=headers,
            json={"title": "Chapter", "summary": "Summary", "position": 1},
        )
        chapter_list = client.get(f"/api/v1/projects/{PROJECT_ID}/volumes/{VOLUME_ID}/chapters")
        chapter_read = client.get(f"/api/v1/chapters/{CHAPTER_ID}")
        chapter_update = client.put(
            f"/api/v1/chapters/{CHAPTER_ID}",
            headers={**headers, "If-Match": '"1"'},
            json={"title": "Chapter 2", "summary": "Summary 2", "position": 2},
        )

    creates = (outline_create, volume_create, chapter_create)
    reads = (outline_read, volume_read, chapter_read)
    updates = (outline_update, volume_update, chapter_update)
    assert all(response.status_code == 201 for response in creates)
    assert all(response.status_code == 200 for response in reads + updates)
    assert all(
        response.headers["Cache-Control"] == "no-store" for response in creates + reads + updates
    )
    assert [response.headers["ETag"] for response in updates] == ['"2"', '"2"', '"2"']
    assert outline_create.headers["Location"].endswith(f"/projects/{PROJECT_ID}/outline")
    assert volume_create.headers["Location"].endswith(f"/volumes/{VOLUME_ID}")
    assert chapter_create.headers["Location"].endswith(f"/chapters/{CHAPTER_ID}")
    assert volume_list.status_code == chapter_list.status_code == 200
    assert (
        volume_list.headers["Cache-Control"] == chapter_list.headers["Cache-Control"] == "no-store"
    )
    assert "ETag" not in volume_list.headers and "ETag" not in chapter_list.headers
    assert len(volume_list.json()) == len(chapter_list.json()) == 1
    assert "content" not in chapter_read.json() and "body" not in chapter_read.json()


def test_chapter_content_routes_use_application_services_and_strong_etags(
    tmp_path: Path,
) -> None:
    command = _CommandSpy()
    query = _QuerySpy()
    with TestClient(_app(tmp_path, command, query)) as client:
        headers = issue_write_headers(client)
        read = client.get(f"/api/v1/chapters/{CHAPTER_ID}/content")
        updated = client.put(
            f"/api/v1/chapters/{CHAPTER_ID}/content",
            headers={**headers, "If-Match": '"1"'},
            json={"content": "New draft"},
        )

    assert read.status_code == updated.status_code == 200
    assert read.headers["ETag"] == '"1"'
    assert updated.headers["ETag"] == '"2"'
    assert read.json()["content"] == "Draft 1"
    assert updated.json()["content"] == "Draft 2"
    assert query.last.chapter_id == CHAPTER_ID
    assert command.last.chapter_id == CHAPTER_ID
    assert command.last.expected_version == 1
    assert command.last.content == "New draft"


def test_chapter_list_rejects_cross_project_volume_before_listing(tmp_path: Path) -> None:
    query = _QuerySpy(owner=SECOND_PROJECT_ID)
    with TestClient(_app(tmp_path, _CommandSpy(), query)) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/volumes/{VOLUME_ID}/chapters")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHAPTER_VOLUME_OWNERSHIP_MISMATCH"
    assert query.list_chapter_calls == 0


@pytest.mark.parametrize(
    ("exc", "resource", "status_code", "code"),
    [
        (OutlineNotFound(), "outline", 404, "OUTLINE_NOT_FOUND"),
        (VolumePositionConflict(), "volume", 409, "VOLUME_POSITION_CONFLICT"),
        (ChapterPositionConflict(), "chapter", 409, "CHAPTER_POSITION_CONFLICT"),
        (
            ConcurrencyConflict(expected_version=1, actual_version=2),
            "chapter",
            412,
            "CHAPTER_VERSION_CONFLICT",
        ),
        (
            ChapterVolumeOwnershipMismatch(),
            "chapter",
            409,
            "CHAPTER_VOLUME_OWNERSHIP_MISMATCH",
        ),
    ],
)
def test_safe_error_mapping(exc, resource, status_code: int, code: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(AppError) as raised:
        raise_novel_structure_http_error(exc, resource=resource)
    assert raised.value.status_code == status_code
    assert raised.value.code == code
    assert "SECRET" not in str(raised.value)


def _database_corruption() -> NovelStructureDataCorruption:
    try:
        raise NovelStructureDataCorruption from OperationalError("statement", {}, Exception())
    except NovelStructureDataCorruption as exc:
        return exc


@pytest.mark.parametrize(
    ("exc", "resource", "status_code", "code"),
    [
        (InvalidNovelStructureTitle(), "outline", 422, "INVALID_NOVEL_STRUCTURE_TITLE"),
        (InvalidNovelStructureSummary(), "outline", 422, "INVALID_NOVEL_STRUCTURE_SUMMARY"),
        (InvalidNovelStructurePosition(), "volume", 422, "INVALID_NOVEL_STRUCTURE_POSITION"),
        (InvalidManuscriptContent(), "chapter", 422, "INVALID_MANUSCRIPT_CONTENT"),
        (ProjectNotFound(project_id(1)), "outline", 404, "PROJECT_NOT_FOUND"),
        (NovelStructureProjectNotFound(), "outline", 404, "PROJECT_NOT_FOUND"),
        (VolumeNotFound(), "volume", 404, "VOLUME_NOT_FOUND"),
        (ChapterNotFound(), "chapter", 404, "CHAPTER_NOT_FOUND"),
        (OutlineAlreadyExists(), "outline", 409, "OUTLINE_ALREADY_EXISTS"),
        (VolumeAlreadyExists(), "volume", 409, "VOLUME_ID_CONFLICT"),
        (ChapterAlreadyExists(), "chapter", 409, "CHAPTER_ID_CONFLICT"),
        (_database_corruption(), "chapter", 503, "NOVEL_STRUCTURE_PERSISTENCE_UNAVAILABLE"),
        (NovelStructureDataCorruption(), "chapter", 500, "NOVEL_STRUCTURE_DATA_CORRUPTION"),
        (
            NovelStructureRepositoryError(),
            "chapter",
            503,
            "NOVEL_STRUCTURE_PERSISTENCE_UNAVAILABLE",
        ),
        (InvalidDomainIdentifier(), "volume", 422, "INVALID_VOLUME_ID"),
    ],
)
def test_all_safe_error_mapping_branches(exc, resource, status_code: int, code: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(AppError) as raised:
        raise_novel_structure_http_error(exc, resource=resource)
    assert raised.value.status_code == status_code
    assert raised.value.code == code


def test_unknown_error_is_not_wrapped() -> None:
    unknown = RuntimeError("opaque")
    with pytest.raises(RuntimeError) as raised:
        raise_novel_structure_http_error(unknown, resource="outline")
    assert raised.value is unknown


class _FailingCommand(_CommandSpy):
    def update_outline(self, command):  # type: ignore[no-untyped-def]
        raise ConcurrencyConflict(expected_version=1, actual_version=2)

    def update_volume(self, command):  # type: ignore[no-untyped-def]
        raise VolumeNotFound


class _FailingQuery(_QuerySpy):
    def get_outline_for_project(self, query):  # type: ignore[no-untyped-def]
        raise OutlineNotFound

    def list_volumes(self, query):  # type: ignore[no-untyped-def]
        raise NovelStructureProjectNotFound

    def get_volume(self, query):  # type: ignore[no-untyped-def]
        raise VolumeNotFound

    def get_chapter(self, query):  # type: ignore[no-untyped-def]
        raise ChapterNotFound


def test_each_read_and_update_route_maps_domain_failures(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path, _FailingCommand(), _FailingQuery())) as client:
        headers = issue_write_headers(client)
        responses = (
            client.get(f"/api/v1/projects/{PROJECT_ID}/outline"),
            client.put(
                f"/api/v1/outlines/{OUTLINE_ID}",
                headers={**headers, "If-Match": '"1"'},
                json={"title": "Outline", "summary": ""},
            ),
            client.get(f"/api/v1/projects/{PROJECT_ID}/volumes"),
            client.get(f"/api/v1/volumes/{VOLUME_ID}"),
            client.put(
                f"/api/v1/volumes/{VOLUME_ID}",
                headers={**headers, "If-Match": '"1"'},
                json={"title": "Volume", "summary": "", "position": 1},
            ),
            client.get(f"/api/v1/chapters/{CHAPTER_ID}"),
        )
    assert [response.status_code for response in responses] == [404, 412, 404, 404, 404, 404]


def test_openapi_inventory_is_exact_and_forbidden_operations_are_absent(tmp_path: Path) -> None:
    app = create_test_app(
        data_root=(tmp_path / "novel-structure-openapi").resolve(),
        expose_api_docs=True,
    )
    schema = app.openapi()
    operations = {
        (method.upper(), path)
        for path, methods in schema["paths"].items()
        for method in methods
        if method in {"get", "post", "put", "patch", "delete"}
    }
    expected = {
        ("POST", "/api/v1/projects/{project_id}/outline"),
        ("GET", "/api/v1/projects/{project_id}/outline"),
        ("PUT", "/api/v1/outlines/{outline_id}"),
        ("POST", "/api/v1/projects/{project_id}/volumes"),
        ("GET", "/api/v1/projects/{project_id}/volumes"),
        ("GET", "/api/v1/volumes/{volume_id}"),
        ("PUT", "/api/v1/volumes/{volume_id}"),
        ("POST", "/api/v1/projects/{project_id}/volumes/{volume_id}/chapters"),
        ("GET", "/api/v1/projects/{project_id}/volumes/{volume_id}/chapters"),
        ("GET", "/api/v1/chapters/{chapter_id}"),
        ("PUT", "/api/v1/chapters/{chapter_id}"),
    }
    assert len(operations) == 99
    assert len(AI_WORKFLOW_OPERATIONS) == 13
    assert len(WRITING_PREPARATION_OPERATIONS) == 9
    assert len(BACKUP_OPERATIONS) == 5
    assert len(WORKBENCH_OPERATIONS) == 5
    assert len(USAGE_OPERATIONS) == 1
    assert len(CANDIDATE_BUDGET_OPERATIONS) == 8
    assert len(STORY_CONTROL_OPERATIONS) == 15
    assert operations >= AI_WORKFLOW_OPERATIONS
    assert operations >= (
        WRITING_PREPARATION_OPERATIONS
        | STORY_MEMORY_OPERATIONS
        | BACKUP_OPERATIONS
        | WORKBENCH_OPERATIONS
        | USAGE_OPERATIONS
        | CANDIDATE_BUDGET_OPERATIONS
        | STORY_CONTROL_OPERATIONS
    )
    assert {
        operation
        for operation in operations
        - (
            WRITING_PREPARATION_OPERATIONS
            | STORY_MEMORY_OPERATIONS
            | BACKUP_OPERATIONS
            | WORKBENCH_OPERATIONS
            | USAGE_OPERATIONS
            | CANDIDATE_BUDGET_OPERATIONS
            | STORY_CONTROL_OPERATIONS
        )
        if any(word in operation[1] for word in ("outline", "volume", "chapter"))
        and not operation[1].endswith("/content")
        and "/ai/" not in operation[1]
    } == expected
    content_operations = {
        ("GET", "/api/v1/chapters/{chapter_id}/content"),
        ("PUT", "/api/v1/chapters/{chapter_id}/content"),
    }
    assert content_operations <= operations
    assert {
        operation
        for operation in operations - AI_WORKFLOW_OPERATIONS - CANDIDATE_BUDGET_OPERATIONS
        if "/ai/" in operation[1]
    } == {
        ("POST", "/api/v1/chapters/{chapter_id}/ai/continue"),
        ("POST", "/api/v1/chapters/{chapter_id}/ai/rewrite"),
    }
    assert ("GET", "/api/v1/outlines/{outline_id}") not in operations
    assert not any(method in {"PATCH", "DELETE"} for method, _ in expected)
    components = schema["components"]["schemas"]
    assert set(components["OutlineResponse"]["properties"]) == {
        "outline_id",
        "project_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "title",
        "summary",
        "created_at",
        "updated_at",
        "revision_created_at",
    }
    assert set(components["VolumeResponse"]["properties"]) == {
        "volume_id",
        "project_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "title",
        "summary",
        "position",
        "created_at",
        "updated_at",
        "revision_created_at",
    }
    assert set(components["ChapterResponse"]["properties"]) == {
        "chapter_id",
        "project_id",
        "volume_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "title",
        "summary",
        "position",
        "created_at",
        "updated_at",
        "revision_created_at",
    }
    assert all(
        "body" not in model["properties"] and "content" not in model["properties"]
        for model in (
            components["OutlineResponse"],
            components["VolumeResponse"],
            components["ChapterResponse"],
        )
    )
    assert set(components["ChapterContentResponse"]["properties"]) == {
        "chapter_id",
        "project_id",
        "volume_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "content",
        "updated_at",
        "revision_created_at",
    }
    assert set(components["UpdateChapterContentRequest"]["properties"]) == {"content"}
    assert components["UpdateChapterContentRequest"]["required"] == ["content"]
    assert components["UpdateChapterContentRequest"]["additionalProperties"] is False
    content_path = schema["paths"]["/api/v1/chapters/{chapter_id}/content"]
    assert set(content_path) == {"get", "put"}
    assert content_path["get"]["tags"] == ["Chapter Writing"]
    assert content_path["put"]["tags"] == ["Chapter Writing"]
    assert (
        next(item for item in content_path["put"]["parameters"] if item["name"] == "If-Match")[
            "required"
        ]
        is True
    )
    assert {"400", "404", "412", "422", "428"} <= set(content_path["put"]["responses"])
    for name, fields in {
        "CreateOutlineRequest": {"title", "summary"},
        "UpdateOutlineRequest": {"title", "summary"},
        "CreateVolumeRequest": {"title", "summary", "position"},
        "UpdateVolumeRequest": {"title", "summary", "position"},
        "CreateChapterRequest": {"title", "summary", "position"},
        "UpdateChapterRequest": {"title", "summary", "position"},
    }.items():
        assert set(components[name]["properties"]) == fields
        assert set(components[name]["required"]) == fields
        assert components[name]["additionalProperties"] is False
    for path in (
        "/api/v1/outlines/{outline_id}",
        "/api/v1/volumes/{volume_id}",
        "/api/v1/chapters/{chapter_id}",
    ):
        put = schema["paths"][path]["put"]
        assert (
            next(item for item in put["parameters"] if item["name"] == "If-Match")["required"]
            is True
        )
        assert {"400", "412", "428"} <= set(put["responses"])


def test_project_path_validation_is_strict() -> None:
    assert get_project_id(PROJECT_ID) == PROJECT_ID
    with pytest.raises(AppError) as raised:
        get_project_id(PROJECT_ID.upper())
    assert raised.value.status_code == 422

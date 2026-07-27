"""Story Bible repository validation, side-effect, and rollback failure tests."""

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from tests.backend.story_bible_repository_support import (
    create_project,
    later,
    repository_database,
    story_bible_aggregate,
    story_bible_revision_id,
    table_state,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleState,
    StoryBibleAlreadyExists,
    StoryBibleDataCorruption,
    StoryBibleForProjectAlreadyExists,
    StoryBibleNotFound,
    StoryBibleProjectNotFound,
    StoryBibleRepositoryError,
)
from aiwebnovel.story_bible.identifiers import StoryBibleRevisionId
from aiwebnovel.story_bible.persistence.models import (
    StoryBibleHeadRecord,
    StoryBibleRecord,
)
from aiwebnovel.story_bible.persistence.repository import (
    SqlAlchemyStoryBibleRepository,
)
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

pytestmark = pytest.mark.integration


def test_constructor_and_invalid_inputs_fail_before_opening_session() -> None:
    with pytest.raises(TypeError):
        SqlAlchemyStoryBibleRepository(None)  # type: ignore[arg-type]

    sessions = 0

    def session_factory():
        nonlocal sessions
        sessions += 1
        raise AssertionError("session must not be opened")

    repository = SqlAlchemyStoryBibleRepository(session_factory)
    with pytest.raises(InvalidStoryBibleState):
        repository.create(object())  # type: ignore[arg-type]
    with pytest.raises(InvalidStoryBibleState):
        repository.get("bad-id")  # type: ignore[arg-type]
    with pytest.raises(InvalidStoryBibleState):
        repository.get_for_project("bad-id")  # type: ignore[arg-type]
    with pytest.raises(InvalidStoryBibleState):
        repository.append_revision(
            story_bible_aggregate().story_bible.id,
            expected_version=ConcurrencyVersion(1),
            title=StoryBibleTitle("Valid"),
            content=StoryBibleContent(),
            clock=None,  # type: ignore[arg-type]
            revision_id_factory=lambda: story_bible_revision_id(1),
        )

    assert sessions == 0


def test_session_factory_failure_is_wrapped_without_details() -> None:
    def fail_session():
        raise RuntimeError("private database path")

    repository = SqlAlchemyStoryBibleRepository(fail_session)

    with pytest.raises(StoryBibleRepositoryError) as captured:
        repository.get(story_bible_aggregate().story_bible.id)

    assert str(captured.value) == "The Story Bible persistence operation could not be completed."
    assert "private" not in str(captured.value)


def test_specific_repository_errors_reject_invalid_identifier_payloads() -> None:
    for error_type in (
        StoryBibleAlreadyExists,
        StoryBibleNotFound,
        StoryBibleForProjectAlreadyExists,
        StoryBibleProjectNotFound,
    ):
        with pytest.raises(InvalidStoryBibleState):
            error_type("invalid")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("method_name", "failure"),
    [
        ("get", SQLAlchemyError("private sql failure")),
        ("get", RuntimeError("private runtime failure")),
        ("get_for_project", SQLAlchemyError("private sql failure")),
        ("get_for_project", RuntimeError("private runtime failure")),
    ],
)
def test_read_failures_are_rolled_back_closed_and_safely_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    failure: Exception,
) -> None:
    closed = 0
    rolled_back = 0
    with repository_database(tmp_path) as database:
        session = database.session_factory()
        original_close = session.close
        original_rollback = session.rollback

        def close() -> None:
            nonlocal closed
            closed += 1
            original_close()

        def rollback() -> None:
            nonlocal rolled_back
            rolled_back += 1
            original_rollback()

        def fail(*_args: object, **_kwargs: object) -> object:
            raise failure

        monkeypatch.setattr(session, "close", close)
        monkeypatch.setattr(session, "rollback", rollback)
        monkeypatch.setattr(session, "execute", fail)
        repository = SqlAlchemyStoryBibleRepository(lambda: session)

        with pytest.raises(StoryBibleRepositoryError) as captured:
            if method_name == "get":
                repository.get(story_bible_aggregate().story_bible.id)
            else:
                repository.get_for_project(story_bible_aggregate().story_bible.project_id)

    assert rolled_back == 1
    assert closed == 1
    assert "private" not in str(captured.value)


@pytest.mark.parametrize("failure_point", ["clock", "id"])
def test_clock_or_identifier_failure_rolls_back_and_calls_in_fixed_order(
    tmp_path: Path,
    failure_point: str,
) -> None:
    initial = story_bible_aggregate()
    calls: list[str] = []

    def clock() -> datetime:
        calls.append("clock")
        if failure_point == "clock":
            raise RuntimeError("private clock failure")
        return later()

    def identifier_factory() -> StoryBibleRevisionId:
        calls.append("id")
        raise RuntimeError("private id failure")

    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        before = table_state(database.engine)
        with pytest.raises(StoryBibleRepositoryError) as captured:
            database.repository.append_revision(
                initial.story_bible.id,
                expected_version=ConcurrencyVersion(1),
                title=StoryBibleTitle("private title"),
                content=StoryBibleContent("private content"),
                clock=clock,
                revision_id_factory=identifier_factory,
            )
        after = table_state(database.engine)

    assert calls == (["clock"] if failure_point == "clock" else ["clock", "id"])
    assert after == before
    assert "private" not in str(captured.value)


def test_success_calls_clock_and_identifier_factory_exactly_once(tmp_path: Path) -> None:
    initial = story_bible_aggregate()
    calls: list[str] = []

    def clock() -> datetime:
        calls.append("clock")
        return later()

    def identifier_factory() -> StoryBibleRevisionId:
        calls.append("id")
        return story_bible_revision_id(30_002)

    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        database.repository.append_revision(
            initial.story_bible.id,
            expected_version=ConcurrencyVersion(1),
            title=StoryBibleTitle("Second"),
            content=StoryBibleContent(),
            clock=clock,
            revision_id_factory=identifier_factory,
        )

    assert calls == ["clock", "id"]


@pytest.mark.parametrize(
    ("operation", "failure_point"),
    [
        ("create", "flush"),
        ("create", "commit"),
        ("append", "flush"),
        ("append", "commit"),
    ],
)
def test_late_session_failure_rolls_back_and_always_closes_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    failure_point: str,
) -> None:
    initial = story_bible_aggregate()
    closed = 0
    with repository_database(tmp_path) as database:
        create_project(database)
        if operation == "append":
            database.repository.create(initial)
        before = table_state(database.engine)
        session = database.session_factory()
        original_close = session.close

        def close() -> None:
            nonlocal closed
            closed += 1
            original_close()

        def fail(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("STORY_BIBLE_PERSISTENCE_SECRET_CANARY")

        monkeypatch.setattr(session, "close", close)
        monkeypatch.setattr(session, failure_point, fail)
        repository = SqlAlchemyStoryBibleRepository(lambda: session)

        with pytest.raises(StoryBibleRepositoryError) as captured:
            if operation == "create":
                repository.create(initial)
            else:
                repository.append_revision(
                    initial.story_bible.id,
                    expected_version=ConcurrencyVersion(1),
                    title=StoryBibleTitle("private late failure"),
                    content=StoryBibleContent("private late failure"),
                    clock=lambda: later(),
                    revision_id_factory=lambda: story_bible_revision_id(30_002),
                )
        after = table_state(database.engine)

    assert closed == 1
    assert after == before
    assert "STORY_BIBLE_PERSISTENCE_SECRET_CANARY" not in str(captured.value)


@pytest.mark.parametrize("cas_target", ["stable", "head"])
def test_cas_miss_rolls_back_inserted_revision_and_pointer_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cas_target: str,
) -> None:
    initial = story_bible_aggregate()

    if cas_target == "stable":

        def miss_stable(*_args: object):
            return (
                update(StoryBibleRecord)
                .values(concurrency_version=StoryBibleRecord.concurrency_version)
                .where(StoryBibleRecord.id.is_(None))
            )

        monkeypatch.setattr(
            "aiwebnovel.story_bible.persistence.repository.story_bible_compare_and_swap",
            miss_stable,
        )
        expected_error: type[Exception] = ConcurrencyConflict
    else:

        def miss_head(*_args: object):
            return (
                update(StoryBibleHeadRecord)
                .values(revision_id=StoryBibleHeadRecord.revision_id)
                .where(StoryBibleHeadRecord.story_bible_id.is_(None))
            )

        monkeypatch.setattr(
            "aiwebnovel.story_bible.persistence.repository.story_bible_head_compare_and_swap",
            miss_head,
        )
        expected_error = StoryBibleDataCorruption

    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        before = table_state(database.engine)
        with pytest.raises(expected_error):
            database.repository.append_revision(
                initial.story_bible.id,
                expected_version=ConcurrencyVersion(1),
                title=StoryBibleTitle("Must roll back"),
                content=StoryBibleContent(),
                clock=lambda: later(),
                revision_id_factory=lambda: story_bible_revision_id(30_002),
            )
        after = table_state(database.engine)

    assert after == before


@pytest.mark.parametrize("cas_target", ["stable", "head"])
def test_cas_miss_resolves_missing_story_bible_after_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cas_target: str,
) -> None:
    initial = story_bible_aggregate()
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        repository = SqlAlchemyStoryBibleRepository(database.session_factory)

        if cas_target == "stable":

            def miss(*_args: object):
                return (
                    update(StoryBibleRecord)
                    .values(concurrency_version=StoryBibleRecord.concurrency_version)
                    .where(StoryBibleRecord.id.is_(None))
                )

            monkeypatch.setattr(
                "aiwebnovel.story_bible.persistence.repository.story_bible_compare_and_swap",
                miss,
            )
        else:

            def miss(*_args: object):
                return (
                    update(StoryBibleHeadRecord)
                    .values(revision_id=StoryBibleHeadRecord.revision_id)
                    .where(StoryBibleHeadRecord.story_bible_id.is_(None))
                )

            monkeypatch.setattr(
                "aiwebnovel.story_bible.persistence.repository.story_bible_head_compare_and_swap",
                miss,
            )

        monkeypatch.setattr(repository, "get", lambda _identifier: None)

        with pytest.raises(StoryBibleNotFound):
            repository.append_revision(
                initial.story_bible.id,
                expected_version=ConcurrencyVersion(1),
                title=StoryBibleTitle("Rolled back"),
                content=StoryBibleContent(),
                clock=lambda: later(),
                revision_id_factory=lambda: story_bible_revision_id(30_002),
            )


def test_repository_runtime_protocol_is_structural() -> None:
    required: tuple[str, ...] = (
        "create",
        "get",
        "get_for_project",
        "append_revision",
    )
    repository_type = SqlAlchemyStoryBibleRepository

    assert all(callable(getattr(repository_type, name)) for name in required)

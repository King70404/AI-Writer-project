"""Detached and explicit Project application snapshot mapping."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime

import pytest
from tests.backend.project_repository_support import aggregate

from aiwebnovel.project.application.mappers import project_snapshot_from_aggregate
from aiwebnovel.project.application.models import ProjectSnapshot

pytestmark = pytest.mark.unit


def test_snapshot_mapping_explicitly_converts_every_current_aggregate_field() -> None:
    current = aggregate(
        52,
        revision_value=1052,
        title="Mapped title",
        description="Mapped description",
        created_at=datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC),
    )

    snapshot = project_snapshot_from_aggregate(current)

    assert snapshot == ProjectSnapshot(
        project_id=str(current.project.id),
        current_revision_id=str(current.current_revision.id),
        revision_number=1,
        concurrency_version=1,
        title="Mapped title",
        description="Mapped description",
        created_at=current.project.created_at,
        updated_at=current.project.updated_at,
        revision_created_at=current.current_revision.created_at,
        head_updated_at=current.head.updated_at,
    )
    assert tuple(field.name for field in fields(snapshot)) == (
        "project_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "title",
        "description",
        "created_at",
        "updated_at",
        "revision_created_at",
        "head_updated_at",
    )


def test_snapshot_contains_only_primitives_and_aware_utc_datetimes() -> None:
    snapshot = project_snapshot_from_aggregate(aggregate(53))

    assert type(snapshot.project_id) is str
    assert type(snapshot.current_revision_id) is str
    assert type(snapshot.revision_number) is int
    assert type(snapshot.concurrency_version) is int
    assert type(snapshot.title) is str
    assert type(snapshot.description) is str
    for timestamp in (
        snapshot.created_at,
        snapshot.updated_at,
        snapshot.revision_created_at,
        snapshot.head_updated_at,
    ):
        assert type(timestamp) is datetime
        assert timestamp.tzinfo is UTC
        assert timestamp.utcoffset() is not None


def test_snapshot_is_frozen_slotted_and_has_no_internal_objects_or_history() -> None:
    snapshot = project_snapshot_from_aggregate(aggregate(54))

    with pytest.raises(FrozenInstanceError):
        snapshot.title = "changed"  # type: ignore[misc]

    assert not hasattr(snapshot, "__dict__")
    assert not hasattr(snapshot, "project")
    assert not hasattr(snapshot, "head")
    assert not hasattr(snapshot, "current_revision")
    assert not hasattr(snapshot, "revisions")
    assert "object at 0x" not in repr(snapshot)


def test_mapping_does_not_modify_source_aggregate() -> None:
    current = aggregate(55)
    original = repr(current)

    project_snapshot_from_aggregate(current)

    assert repr(current) == original

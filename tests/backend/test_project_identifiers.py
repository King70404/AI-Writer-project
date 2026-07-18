"""Tests for the two nominal Project-owned identifier types."""

import ast
from pathlib import Path
from typing import get_type_hints

import pytest

import aiwebnovel.project.identifiers as identifier_module
from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.domain.identifiers import MonotonicUlidGenerator, PrefixedUlid, Ulid
from aiwebnovel.project.entities import Project, ProjectHead, ProjectRevision
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId

pytestmark = pytest.mark.unit

RAW_ULID = Ulid.parse("01ARZ3NDEKTSV4RRFFQ69G5FAV")


def test_project_identifier_types_have_fixed_distinct_prefixes() -> None:
    project_id = ProjectId.from_ulid(RAW_ULID)
    revision_id = ProjectRevisionId.from_ulid(RAW_ULID)

    assert str(project_id) == f"prj_{RAW_ULID}"
    assert str(revision_id) == f"prv_{RAW_ULID}"
    assert project_id.prefix == "prj"
    assert revision_id.prefix == "prv"
    assert project_id.ulid == revision_id.ulid == RAW_ULID
    assert type(project_id) is ProjectId
    assert type(revision_id) is ProjectRevisionId
    assert project_id != revision_id
    assert len({project_id, revision_id}) == 2


def test_project_identifier_parse_normalizes_and_rejects_wrong_prefix() -> None:
    project_text = f"prj_{str(RAW_ULID).lower()}"
    revision_text = f"prv_{str(RAW_ULID).lower()}"

    assert ProjectId.parse(project_text) == ProjectId.from_ulid(RAW_ULID)
    assert ProjectRevisionId.parse(revision_text) == ProjectRevisionId.from_ulid(RAW_ULID)
    with pytest.raises(InvalidDomainIdentifier):
        ProjectId.parse(revision_text)
    with pytest.raises(InvalidDomainIdentifier):
        ProjectRevisionId.parse(project_text)


def test_project_identifier_new_accepts_a_deterministic_generator() -> None:
    generator = MonotonicUlidGenerator(
        clock=lambda: 123_456,
        random_source=lambda _bits: 9,
    )

    first = ProjectId.new(generator)
    second = ProjectId.new(generator)
    revision = ProjectRevisionId.new(generator)

    assert type(first) is ProjectId
    assert type(revision) is ProjectRevisionId
    assert first < second
    assert [first.ulid.randomness, second.ulid.randomness, revision.ulid.randomness] == [9, 10, 11]


def test_project_identifiers_are_immutable_sortable_and_hashable() -> None:
    low = ProjectId.from_ulid(Ulid.from_int(1))
    high = ProjectId.from_ulid(Ulid.from_int(2))

    assert sorted([high, low]) == [low, high]
    assert {low: "project"}[ProjectId.parse(str(low))] == "project"
    with pytest.raises(AttributeError, match="immutable"):
        low.prefix = "prv"


def test_generic_prefixed_value_is_not_a_nominal_project_identifier() -> None:
    generic = PrefixedUlid("prj", RAW_ULID)
    nominal = ProjectId.from_ulid(RAW_ULID)

    assert generic != nominal
    assert type(generic) is PrefixedUlid


def test_project_public_entity_annotations_use_concrete_identifier_types() -> None:
    project_hints = get_type_hints(Project)
    revision_hints = get_type_hints(ProjectRevision)
    head_hints = get_type_hints(ProjectHead)

    assert project_hints["id"] is ProjectId
    assert revision_hints["id"] is ProjectRevisionId
    assert revision_hints["project_id"] is ProjectId
    assert head_hints["project_id"] is ProjectId
    assert head_hints["revision_id"] is ProjectRevisionId
    assert all(value is not PrefixedUlid for value in project_hints.values())


def test_each_business_prefix_is_declared_by_the_factory_exactly_once() -> None:
    source_root = Path(identifier_module.__file__).resolve().parents[1]
    declarations: list[tuple[str, str, Path]] = []
    for module_path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            called_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            if called_name != "create_prefixed_ulid_type":
                continue
            type_name, prefix = node.args[:2]
            if (
                isinstance(type_name, ast.Constant)
                and isinstance(type_name.value, str)
                and isinstance(prefix, ast.Constant)
                and isinstance(prefix.value, str)
                and prefix.value in {"prj", "prv"}
            ):
                declarations.append((type_name.value, prefix.value, module_path))

    assert [(type_name, prefix) for type_name, prefix, _path in declarations] == [
        ("ProjectId", "prj"),
        ("ProjectRevisionId", "prv"),
    ]
    assert {path for _type_name, _prefix, path in declarations} == {
        Path(identifier_module.__file__).resolve()
    }


def test_identifier_constructors_reject_raw_or_wrong_domain_values() -> None:
    with pytest.raises(InvalidDomainIdentifier):
        ProjectId.from_ulid("not-an-ulid")
    with pytest.raises(InvalidDomainIdentifier):
        ProjectRevisionId.from_ulid(ProjectId.from_ulid(RAW_ULID))

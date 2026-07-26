"""Story Bible identifier prefix, canonical-text, and privacy tests."""

from collections.abc import Callable

import pytest

from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.domain.identifiers import MonotonicUlidGenerator, Ulid
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId

CANONICAL_ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


@pytest.mark.parametrize(
    ("identifier_type", "prefix"),
    [
        (StoryBibleId, "sbl"),
        (StoryBibleRevisionId, "sbr"),
    ],
)
def test_new_generates_canonical_identifier(
    identifier_type: type[StoryBibleId] | type[StoryBibleRevisionId],
    prefix: str,
) -> None:
    generator = MonotonicUlidGenerator(clock=lambda: 1, random_source=lambda _bits: 1)

    identifier = identifier_type.new(generator)

    assert type(identifier) is identifier_type
    assert str(identifier).startswith(f"{prefix}_")
    assert str(identifier) == str(identifier).upper().replace(prefix.upper(), prefix, 1)


@pytest.mark.parametrize(
    ("identifier_type", "canonical"),
    [
        (StoryBibleId, f"sbl_{CANONICAL_ULID}"),
        (StoryBibleRevisionId, f"sbr_{CANONICAL_ULID}"),
    ],
)
def test_parse_round_trips_only_canonical_text(
    identifier_type: type[StoryBibleId] | type[StoryBibleRevisionId],
    canonical: str,
) -> None:
    parsed = identifier_type.parse(canonical)

    assert str(parsed) == canonical
    assert identifier_type.parse(str(parsed)) == parsed
    assert hash(identifier_type.parse(canonical)) == hash(parsed)


def test_identifier_types_are_nominally_distinct() -> None:
    shared_ulid = Ulid.parse(CANONICAL_ULID)
    bible_id = StoryBibleId.from_ulid(shared_ulid)
    revision = StoryBibleRevisionId.from_ulid(shared_ulid)

    assert bible_id != revision
    assert len({bible_id, revision}) == 2


@pytest.mark.parametrize(
    ("parser", "text"),
    [
        (StoryBibleId.parse, f"sbr_{CANONICAL_ULID}"),
        (StoryBibleRevisionId.parse, f"sbl_{CANONICAL_ULID}"),
        (StoryBibleId.parse, f"prj_{CANONICAL_ULID}"),
        (StoryBibleId.parse, CANONICAL_ULID),
        (StoryBibleId.parse, f"sbl_{CANONICAL_ULID.lower()}"),
        (StoryBibleId.parse, f"SBL_{CANONICAL_ULID}"),
        (StoryBibleId.parse, f" sbl_{CANONICAL_ULID}"),
        (StoryBibleId.parse, f"sbl_{CANONICAL_ULID}\n"),
        (StoryBibleId.parse, ""),
    ],
)
def test_parse_rejects_wrong_prefix_or_noncanonical_text(
    parser: Callable[[str], object],
    text: str,
) -> None:
    with pytest.raises(InvalidDomainIdentifier) as caught:
        parser(text)

    if text:
        assert text not in str(caught.value)


@pytest.mark.parametrize("value", [None, 1, True, b"sbl_bad", object()])
def test_parse_rejects_non_strings_without_echoing_them(value: object) -> None:
    with pytest.raises(InvalidDomainIdentifier):
        StoryBibleId.parse(value)  # type: ignore[arg-type]


def test_hostile_repr_is_never_called() -> None:
    class Hostile:
        def __repr__(self) -> str:
            raise AssertionError("repr must not be called")

    with pytest.raises(InvalidDomainIdentifier):
        StoryBibleRevisionId.parse(Hostile())  # type: ignore[arg-type]


def test_project_identifier_cannot_be_used_as_story_bible_identifier() -> None:
    project = ProjectId.from_ulid(Ulid.parse(CANONICAL_ULID))

    with pytest.raises(InvalidDomainIdentifier):
        StoryBibleId.parse(str(project))

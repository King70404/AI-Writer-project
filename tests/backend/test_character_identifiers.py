"""Strict Character identifier contracts."""

import pytest
from tests.backend.character_support import character_id, revision_id

from aiwebnovel.character import CharacterId, CharacterRevisionId
from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.identifiers import StoryBibleId

CANARY = "CHARACTER_SECRET_CANARY"


class Hostile:
    """Fail if rejected input is rendered."""

    def __str__(self) -> str:
        raise AssertionError("hostile str called")

    def __repr__(self) -> str:
        raise AssertionError("hostile repr called")


@pytest.mark.parametrize(
    ("identifier_type", "prefix"),
    [(CharacterId, "chr_"), (CharacterRevisionId, "crv_")],
)
def test_new_ids_are_canonical_and_round_trip(identifier_type: type, prefix: str) -> None:
    value = identifier_type.new()
    text = str(value)

    assert text.startswith(prefix)
    assert identifier_type.parse(text) == value
    assert hash(identifier_type.parse(text)) == hash(value)
    assert not hasattr(value, "__dict__")


def test_nominal_character_ids_are_distinct() -> None:
    stable = character_id()
    revision = revision_id()

    assert stable != revision
    with pytest.raises(InvalidDomainIdentifier):
        CharacterRevisionId.parse(str(stable))
    with pytest.raises(InvalidDomainIdentifier):
        CharacterId.parse(str(revision))


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "chr",
        "chr_",
        "chr_00000000000000000000000001 ",
        " chr_00000000000000000000000001",
        "CHR_00000000000000000000000001",
        "chr_0000000000000000000000000",
        "chr_000000000000000000000000011",
        "chr_0000000000000000000000000i",
        "chr_0000000000000000000000000l",
        "00000000000000000000000001",
        "prj_00000000000000000000000001",
        "sbl_00000000000000000000000001",
        "crv_00000000000000000000000001",
        "chr_0000000000000000000000000a",
        "chr_00000000000000000000000001\n",
    ],
)
def test_character_id_rejects_noncanonical_text(text: str) -> None:
    with pytest.raises(InvalidDomainIdentifier) as caught:
        CharacterId.parse(text)

    assert str(caught.value) == "The domain identifier is invalid."


@pytest.mark.parametrize("value", [None, 1, True, b"chr", Hostile()])
def test_identifier_rejects_non_string_without_rendering(value: object) -> None:
    with pytest.raises(InvalidDomainIdentifier):
        CharacterId.parse(value)  # type: ignore[arg-type]


def test_other_nominal_ids_cannot_substitute_for_character_id() -> None:
    project = ProjectId.parse("prj_00000000000000000000000001")
    story_bible = StoryBibleId.parse("sbl_00000000000000000000000001")

    assert type(project) is not CharacterId
    assert type(story_bible) is not CharacterId
    with pytest.raises(InvalidDomainIdentifier):
        CharacterId.from_ulid(project)  # type: ignore[arg-type]


def test_identifier_error_does_not_echo_secret_input() -> None:
    secret = f"chr_{CANARY}"

    with pytest.raises(InvalidDomainIdentifier) as caught:
        CharacterId.parse(secret)

    assert CANARY not in str(caught.value)
    assert CANARY not in repr(caught.value)

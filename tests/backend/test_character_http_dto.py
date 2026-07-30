"""Strict immutable Character HTTP DTO contracts."""

from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError
from tests.backend.character_http_support import BASE_TIME, PROJECT_ID, snapshot

from aiwebnovel.character.web.dto import (
    CharacterListItemResponse,
    CharacterListPageResponse,
    CharacterResponse,
    CreateCharacterRequest,
    ReviseCharacterRequest,
)
from aiwebnovel.character.web.mappers import character_response_from_snapshot


def _complete_payload() -> dict[str, object]:
    return character_response_from_snapshot(snapshot()).model_dump()


def test_create_and_revise_requests_are_strict_frozen_complete_models() -> None:
    create = CreateCharacterRequest.model_validate({"name": "A"})
    assert create.model_dump() == {"name": "A", "role": "", "profile": ""}
    with pytest.raises(ValidationError):
        CreateCharacterRequest.model_validate({"name": True})
    with pytest.raises(ValidationError):
        CreateCharacterRequest.model_validate({"name": "A", "extra": "no"})
    with pytest.raises(ValidationError):
        ReviseCharacterRequest.model_validate({"name": "A", "role": "R"})
    revise = ReviseCharacterRequest(name="A", role="", profile="")
    with pytest.raises((ValidationError, FrozenInstanceError)):
        revise.name = "B"  # type: ignore[misc]


def test_complete_response_is_strict_consistent_and_private_on_failure() -> None:
    response = character_response_from_snapshot(snapshot())
    assert response.profile == "Initial profile"
    with pytest.raises(ValidationError) as error:
        CharacterResponse.model_validate({**response.model_dump(), "concurrency_version": True})
    assert "Initial profile" not in str(error.value)
    with pytest.raises(ValidationError):
        CharacterResponse.model_validate({**response.model_dump(), "concurrency_version": 2})
    with pytest.raises(ValidationError):
        CharacterResponse.model_validate(
            {**response.model_dump(), "updated_at": BASE_TIME.replace(tzinfo=None)}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("character_id", "bad"),
        ("project_id", "bad"),
        ("current_revision_id", "bad"),
        ("revision_number", 0),
        ("concurrency_version", 0),
        ("name", ""),
        ("name", " Character "),
        ("role", " Role "),
        ("profile", "line\r\nbreak"),
        ("created_at", BASE_TIME.astimezone().replace(tzinfo=None)),
    ],
)
def test_complete_response_rejects_noncanonical_fields(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        CharacterResponse.model_validate({**_complete_payload(), field: value})


def test_complete_response_rejects_non_utc_and_inconsistent_times() -> None:
    from datetime import timedelta, timezone

    with pytest.raises(ValidationError):
        CharacterResponse.model_validate(
            {
                **_complete_payload(),
                "created_at": BASE_TIME.astimezone(timezone(timedelta(hours=8))),
            }
        )
    with pytest.raises(ValidationError):
        CharacterResponse.model_validate(
            {
                **_complete_payload(),
                "created_at": BASE_TIME.replace(year=2027),
            }
        )


def test_list_dtos_omit_profile_total_and_enforce_cursor_consistency() -> None:
    item = CharacterListItemResponse(
        character_id=snapshot().character_id,
        current_revision_id=snapshot().current_revision_id,
        revision_number=1,
        concurrency_version=1,
        name="Character",
        role="Protagonist",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    page = CharacterListPageResponse(
        project_id=PROJECT_ID,
        items=(item,),
        next_cursor=None,
        has_more=False,
    )
    assert "profile" not in item.model_dump()
    assert "total" not in page.model_dump()
    with pytest.raises(ValidationError):
        CharacterListPageResponse(
            project_id=PROJECT_ID,
            items=(item,),
            next_cursor=None,
            has_more=True,
        )
    with pytest.raises(ValidationError):
        CharacterListItemResponse(**{**item.model_dump(), "concurrency_version": 2})
    with pytest.raises(ValidationError):
        CharacterListItemResponse(
            **{
                **item.model_dump(),
                "created_at": BASE_TIME.replace(year=2027),
            }
        )
    with pytest.raises(ValidationError):
        CharacterListPageResponse(
            project_id=PROJECT_ID,
            items=(item,),
            next_cursor="unexpected",
            has_more=False,
        )

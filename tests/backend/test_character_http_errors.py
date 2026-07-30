"""Safe Character-to-HTTP error mapping."""

import pytest
from sqlalchemy.exc import OperationalError
from tests.backend.character_repository_support import character_id, project_id

from aiwebnovel.character.errors import (
    CharacterAlreadyExists,
    CharacterDataCorruption,
    CharacterNotFound,
    CharacterProjectNotFound,
    CharacterRepositoryError,
    InvalidCharacterName,
    InvalidCharacterProfile,
    InvalidCharacterRole,
)
from aiwebnovel.character.web.errors import raise_character_http_error
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import ConcurrencyConflict


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (InvalidCharacterName(), 422, "INVALID_CHARACTER_NAME"),
        (InvalidCharacterRole(), 422, "INVALID_CHARACTER_ROLE"),
        (InvalidCharacterProfile(), 422, "INVALID_CHARACTER_PROFILE"),
        (CharacterProjectNotFound(project_id(1)), 404, "PROJECT_NOT_FOUND"),
        (CharacterNotFound(character_id(1)), 404, "CHARACTER_NOT_FOUND"),
        (CharacterAlreadyExists(character_id(1)), 409, "CHARACTER_ID_CONFLICT"),
        (
            ConcurrencyConflict(expected_version=1, actual_version=2),
            412,
            "CHARACTER_VERSION_CONFLICT",
        ),
        (CharacterDataCorruption(), 500, "CHARACTER_DATA_CORRUPTION"),
        (CharacterRepositoryError(), 503, "CHARACTER_PERSISTENCE_UNAVAILABLE"),
    ],
)
def test_known_errors_map_to_stable_private_app_errors(
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    with pytest.raises(AppError) as raised:
        raise_character_http_error(error)
    assert raised.value.status_code == status_code
    assert raised.value.code == code
    assert "CHARACTER_HTTP_SECRET_CANARY" not in str(raised.value)


def test_driver_caused_corruption_is_service_unavailable() -> None:
    try:
        try:
            raise OperationalError("statement", {}, RuntimeError("driver"))
        except OperationalError as cause:
            raise CharacterDataCorruption from cause
    except CharacterDataCorruption as error:
        with pytest.raises(AppError) as raised:
            raise_character_http_error(error)
    assert raised.value.status_code == 503


def test_unknown_error_is_not_wrapped() -> None:
    error = RuntimeError("opaque")
    with pytest.raises(RuntimeError) as raised:
        raise_character_http_error(error)
    assert raised.value is error

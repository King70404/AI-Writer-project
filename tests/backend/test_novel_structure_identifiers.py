"""Strict nominal identifiers for novel structure."""

import pytest

from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.novel_structure import (
    ChapterId,
    ChapterRevisionId,
    OutlineId,
    OutlineRevisionId,
    VolumeId,
    VolumeRevisionId,
)


@pytest.mark.parametrize(
    ("identifier_type", "prefix"),
    [
        (OutlineId, "out_"),
        (OutlineRevisionId, "orv_"),
        (VolumeId, "vol_"),
        (VolumeRevisionId, "vrv_"),
        (ChapterId, "chp_"),
        (ChapterRevisionId, "chv_"),
    ],
)
def test_identifiers_are_canonical_nominal_prefixed_ulids(
    identifier_type: type,
    prefix: str,
) -> None:
    value = identifier_type.new()
    text = str(value)

    assert text.startswith(prefix)
    assert identifier_type.parse(text) == value
    assert not hasattr(value, "__dict__")


@pytest.mark.parametrize(
    "identifier_type",
    [OutlineId, OutlineRevisionId, VolumeId, VolumeRevisionId, ChapterId, ChapterRevisionId],
)
def test_identifiers_reject_noncanonical_text(identifier_type: type) -> None:
    canonical = str(identifier_type.new())

    for value in (canonical.lower(), f" {canonical}", f"{canonical}\n", None, True):
        with pytest.raises(InvalidDomainIdentifier):
            identifier_type.parse(value)


def test_all_six_identifier_types_are_distinct() -> None:
    values = [
        OutlineId.new(),
        OutlineRevisionId.new(),
        VolumeId.new(),
        VolumeRevisionId.new(),
        ChapterId.new(),
        ChapterRevisionId.new(),
    ]

    assert len(set(values)) == 6
    for target_type in (
        OutlineId,
        OutlineRevisionId,
        VolumeId,
        VolumeRevisionId,
        ChapterId,
        ChapterRevisionId,
    ):
        for value in values:
            if type(value) is not target_type:
                with pytest.raises(InvalidDomainIdentifier):
                    target_type.parse(str(value))

"""Nominal Outline, Volume, and Chapter identifiers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self, final

from aiwebnovel.domain.identifiers import PrefixedUlid, Ulid, create_prefixed_ulid_type

if TYPE_CHECKING:

    @final
    class OutlineId(PrefixedUlid):
        def __init__(self, ulid: Ulid) -> None: ...

        @classmethod
        def parse(cls, text: str) -> Self: ...

        @classmethod
        def from_ulid(cls, ulid: Ulid) -> Self: ...

    @final
    class OutlineRevisionId(PrefixedUlid):
        def __init__(self, ulid: Ulid) -> None: ...

        @classmethod
        def parse(cls, text: str) -> Self: ...

        @classmethod
        def from_ulid(cls, ulid: Ulid) -> Self: ...

    @final
    class VolumeId(PrefixedUlid):
        def __init__(self, ulid: Ulid) -> None: ...

        @classmethod
        def parse(cls, text: str) -> Self: ...

        @classmethod
        def from_ulid(cls, ulid: Ulid) -> Self: ...

    @final
    class VolumeRevisionId(PrefixedUlid):
        def __init__(self, ulid: Ulid) -> None: ...

        @classmethod
        def parse(cls, text: str) -> Self: ...

        @classmethod
        def from_ulid(cls, ulid: Ulid) -> Self: ...

    @final
    class ChapterId(PrefixedUlid):
        def __init__(self, ulid: Ulid) -> None: ...

        @classmethod
        def parse(cls, text: str) -> Self: ...

        @classmethod
        def from_ulid(cls, ulid: Ulid) -> Self: ...

    @final
    class ChapterRevisionId(PrefixedUlid):
        def __init__(self, ulid: Ulid) -> None: ...

        @classmethod
        def parse(cls, text: str) -> Self: ...

        @classmethod
        def from_ulid(cls, ulid: Ulid) -> Self: ...

else:

    def _create_strict_identifier_type(type_name: str, prefix: str) -> type[PrefixedUlid]:
        base_type = create_prefixed_ulid_type(type_name, prefix)

        def parse(cls: type[PrefixedUlid], text: str) -> PrefixedUlid:
            parsed = base_type.parse(text)
            if type(text) is not str or str(parsed) != text:
                from aiwebnovel.domain.errors import InvalidDomainIdentifier

                raise InvalidDomainIdentifier
            return cls.from_ulid(parsed.ulid)

        return type(
            type_name,
            (base_type,),
            {"__module__": __name__, "__slots__": (), "parse": classmethod(parse)},
        )

    OutlineId = _create_strict_identifier_type("OutlineId", "out")
    OutlineRevisionId = _create_strict_identifier_type("OutlineRevisionId", "orv")
    VolumeId = _create_strict_identifier_type("VolumeId", "vol")
    VolumeRevisionId = _create_strict_identifier_type("VolumeRevisionId", "vrv")
    ChapterId = _create_strict_identifier_type("ChapterId", "chp")
    ChapterRevisionId = _create_strict_identifier_type("ChapterRevisionId", "chv")


__all__ = [
    "ChapterId",
    "ChapterRevisionId",
    "OutlineId",
    "OutlineRevisionId",
    "VolumeId",
    "VolumeRevisionId",
]

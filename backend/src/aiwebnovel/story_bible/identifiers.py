"""Nominal Story Bible identifiers backed by the shared ULID factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self, final

from aiwebnovel.domain.identifiers import PrefixedUlid, Ulid, create_prefixed_ulid_type

if TYPE_CHECKING:

    @final
    class StoryBibleId(PrefixedUlid):
        """Static nominal contract for the runtime ``sbl`` identifier type."""

        def __init__(self, ulid: Ulid) -> None: ...

        @classmethod
        def parse(cls, text: str) -> Self: ...

        @classmethod
        def from_ulid(cls, ulid: Ulid) -> Self: ...

    @final
    class StoryBibleRevisionId(PrefixedUlid):
        """Static nominal contract for the runtime ``sbr`` identifier type."""

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
            {
                "__module__": __name__,
                "__slots__": (),
                "parse": classmethod(parse),
            },
        )

    StoryBibleId = _create_strict_identifier_type("StoryBibleId", "sbl")
    StoryBibleRevisionId = _create_strict_identifier_type("StoryBibleRevisionId", "sbr")

__all__ = ["StoryBibleId", "StoryBibleRevisionId"]

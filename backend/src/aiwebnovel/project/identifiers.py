"""Nominal Project identifier declarations backed by the shared ULID factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self, final

from aiwebnovel.domain.identifiers import PrefixedUlid, Ulid, create_prefixed_ulid_type

if TYPE_CHECKING:

    @final
    class ProjectId(PrefixedUlid):
        """Static nominal contract for the runtime ``prj`` identifier type."""

        def __init__(self, ulid: Ulid) -> None: ...

        @classmethod
        def parse(cls, text: str) -> Self: ...

        @classmethod
        def from_ulid(cls, ulid: Ulid) -> Self: ...

    @final
    class ProjectRevisionId(PrefixedUlid):
        """Static nominal contract for the runtime ``prv`` identifier type."""

        def __init__(self, ulid: Ulid) -> None: ...

        @classmethod
        def parse(cls, text: str) -> Self: ...

        @classmethod
        def from_ulid(cls, ulid: Ulid) -> Self: ...

else:
    ProjectId = create_prefixed_ulid_type("ProjectId", "prj")
    ProjectRevisionId = create_prefixed_ulid_type("ProjectRevisionId", "prv")

__all__ = ["ProjectId", "ProjectRevisionId"]

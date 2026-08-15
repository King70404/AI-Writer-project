"""Public pure-Python novel-structure application contracts."""

from aiwebnovel.novel_structure.application.commands import (
    CreateChapterCommand,
    CreateOutlineCommand,
    CreateVolumeCommand,
    UpdateChapterCommand,
    UpdateOutlineCommand,
    UpdateVolumeCommand,
)
from aiwebnovel.novel_structure.application.mappers import (
    chapter_snapshot_from_aggregate,
    outline_snapshot_from_aggregate,
    volume_snapshot_from_aggregate,
)
from aiwebnovel.novel_structure.application.models import (
    ChapterSnapshot,
    OutlineSnapshot,
    VolumeSnapshot,
)
from aiwebnovel.novel_structure.application.queries import (
    GetChapterQuery,
    GetOutlineForProjectQuery,
    GetOutlineQuery,
    GetVolumeQuery,
    ListChaptersQuery,
    ListVolumesQuery,
)
from aiwebnovel.novel_structure.application.services import (
    NovelStructureCommandService,
    NovelStructureQueryService,
)

__all__ = [
    "ChapterSnapshot",
    "CreateChapterCommand",
    "CreateOutlineCommand",
    "CreateVolumeCommand",
    "GetChapterQuery",
    "GetOutlineForProjectQuery",
    "GetOutlineQuery",
    "GetVolumeQuery",
    "ListChaptersQuery",
    "ListVolumesQuery",
    "NovelStructureCommandService",
    "NovelStructureQueryService",
    "OutlineSnapshot",
    "UpdateChapterCommand",
    "UpdateOutlineCommand",
    "UpdateVolumeCommand",
    "VolumeSnapshot",
    "chapter_snapshot_from_aggregate",
    "outline_snapshot_from_aggregate",
    "volume_snapshot_from_aggregate",
]

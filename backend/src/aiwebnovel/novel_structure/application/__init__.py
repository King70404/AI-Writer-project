"""Public pure-Python novel-structure application contracts."""

from aiwebnovel.novel_structure.application.commands import (
    CreateChapterCommand,
    CreateOutlineCommand,
    CreateVolumeCommand,
    UpdateChapterCommand,
    UpdateChapterContentCommand,
    UpdateOutlineCommand,
    UpdateVolumeCommand,
)
from aiwebnovel.novel_structure.application.mappers import (
    chapter_content_snapshot_from_aggregate,
    chapter_snapshot_from_aggregate,
    outline_snapshot_from_aggregate,
    volume_snapshot_from_aggregate,
)
from aiwebnovel.novel_structure.application.models import (
    ChapterContentSnapshot,
    ChapterSnapshot,
    OutlineSnapshot,
    VolumeSnapshot,
)
from aiwebnovel.novel_structure.application.queries import (
    GetChapterContentQuery,
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
    "ChapterContentSnapshot",
    "ChapterSnapshot",
    "CreateChapterCommand",
    "CreateOutlineCommand",
    "CreateVolumeCommand",
    "GetChapterContentQuery",
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
    "UpdateChapterContentCommand",
    "UpdateOutlineCommand",
    "UpdateVolumeCommand",
    "VolumeSnapshot",
    "chapter_content_snapshot_from_aggregate",
    "chapter_snapshot_from_aggregate",
    "outline_snapshot_from_aggregate",
    "volume_snapshot_from_aggregate",
]

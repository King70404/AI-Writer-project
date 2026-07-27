"""Public framework-independent Story Bible domain contracts."""

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidDomainIdentifier
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.entities import (
    StoryBible,
    StoryBibleAggregate,
    StoryBibleHead,
    StoryBibleRevision,
)
from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleContent,
    InvalidStoryBibleState,
    InvalidStoryBibleTitle,
    StoryBibleAlreadyExists,
    StoryBibleDataCorruption,
    StoryBibleDomainError,
    StoryBibleForProjectAlreadyExists,
    StoryBibleNotFound,
    StoryBibleProjectNotFound,
    StoryBibleRepositoryError,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.repository import StoryBibleRepository
from aiwebnovel.story_bible.transitions import (
    append_story_bible_revision,
    create_initial_story_bible,
)
from aiwebnovel.story_bible.values import (
    StoryBibleContent,
    StoryBibleTitle,
)

__all__ = [
    "ConcurrencyConflict",
    "ConcurrencyVersion",
    "InvalidDomainIdentifier",
    "InvalidStoryBibleContent",
    "InvalidStoryBibleState",
    "InvalidStoryBibleTitle",
    "ProjectId",
    "RevisionNumber",
    "StoryBible",
    "StoryBibleAggregate",
    "StoryBibleAlreadyExists",
    "StoryBibleContent",
    "StoryBibleDataCorruption",
    "StoryBibleDomainError",
    "StoryBibleForProjectAlreadyExists",
    "StoryBibleHead",
    "StoryBibleId",
    "StoryBibleNotFound",
    "StoryBibleProjectNotFound",
    "StoryBibleRepository",
    "StoryBibleRepositoryError",
    "StoryBibleRevision",
    "StoryBibleRevisionId",
    "StoryBibleTitle",
    "append_story_bible_revision",
    "create_initial_story_bible",
]

"""Safe framework-independent failures owned by the novel-structure domain."""

from aiwebnovel.domain.errors import DomainError


class NovelStructureDomainError(DomainError):
    """Base class for expected novel-structure domain failures."""

    code = "novel_structure_domain_error"
    message = "The novel structure domain operation could not be completed."


class InvalidNovelStructureTitle(NovelStructureDomainError):
    """Raised when a structure title violates its value rules."""

    code = "invalid_novel_structure_title"
    message = "The novel structure title is invalid."


class InvalidNovelStructureSummary(NovelStructureDomainError):
    """Raised when a structure summary violates its value rules."""

    code = "invalid_novel_structure_summary"
    message = "The novel structure summary is invalid."


class InvalidNovelStructurePosition(NovelStructureDomainError):
    """Raised when a Volume or Chapter position is invalid."""

    code = "invalid_novel_structure_position"
    message = "The novel structure position is invalid."


class InvalidNovelStructureState(NovelStructureDomainError):
    """Raised when structure objects cannot form one valid state."""

    code = "invalid_novel_structure_state"
    message = "The novel structure state is invalid."

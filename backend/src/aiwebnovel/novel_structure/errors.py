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


class NovelStructureRepositoryError(NovelStructureDomainError):
    """Base class for safe novel-structure persistence failures."""

    code = "novel_structure_repository_error"
    message = "The novel structure persistence operation could not be completed."


class NovelStructureDataCorruption(NovelStructureRepositoryError):
    code = "novel_structure_data_corruption"
    message = "The stored novel structure state is inconsistent."


class NovelStructureProjectNotFound(NovelStructureRepositoryError):
    code = "novel_structure_project_not_found"
    message = "The owning Project was not found."


class OutlineAlreadyExists(NovelStructureRepositoryError):
    code = "outline_already_exists"
    message = "The Outline already exists for this identity or Project."


class OutlineNotFound(NovelStructureRepositoryError):
    code = "outline_not_found"
    message = "The Outline was not found."


class VolumeAlreadyExists(NovelStructureRepositoryError):
    code = "volume_already_exists"
    message = "The Volume already exists."


class VolumeNotFound(NovelStructureRepositoryError):
    code = "volume_not_found"
    message = "The Volume was not found."


class VolumePositionConflict(NovelStructureRepositoryError):
    code = "volume_position_conflict"
    message = "The Volume position is already occupied."


class ChapterAlreadyExists(NovelStructureRepositoryError):
    code = "chapter_already_exists"
    message = "The Chapter already exists."


class ChapterNotFound(NovelStructureRepositoryError):
    code = "chapter_not_found"
    message = "The Chapter was not found."


class ChapterPositionConflict(NovelStructureRepositoryError):
    code = "chapter_position_conflict"
    message = "The Chapter position is already occupied."


class ChapterVolumeOwnershipMismatch(NovelStructureRepositoryError):
    code = "chapter_volume_ownership_mismatch"
    message = "The Chapter and Volume Project ownership does not match."

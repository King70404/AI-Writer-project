"""Safe framework-independent failures owned by the Story Bible domain."""

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.identifiers import StoryBibleId


class StoryBibleDomainError(DomainError):
    """Base class for expected Story Bible domain failures."""

    code = "story_bible_domain_error"
    message = "The Story Bible domain operation could not be completed."


class InvalidStoryBibleTitle(StoryBibleDomainError):
    """Raised when a Story Bible title violates its value rules."""

    code = "invalid_story_bible_title"
    message = "The Story Bible title is invalid."


class InvalidStoryBibleContent(StoryBibleDomainError):
    """Raised when Story Bible content violates its value rules."""

    code = "invalid_story_bible_content"
    message = "The Story Bible content is invalid."


class InvalidStoryBibleState(StoryBibleDomainError):
    """Raised when Story Bible objects cannot form one valid state."""

    code = "invalid_story_bible_state"
    message = "The Story Bible state is invalid."


class StoryBibleRepositoryError(StoryBibleDomainError):
    """Base class for safe Story Bible persistence-boundary failures."""

    code = "story_bible_repository_error"
    message = "The Story Bible persistence operation could not be completed."


class StoryBibleAlreadyExists(StoryBibleRepositoryError):
    """Raised when create would reuse a stable Story Bible identity."""

    code = "story_bible_already_exists"
    message = "The Story Bible already exists."

    def __init__(self, story_bible_id: StoryBibleId) -> None:
        if type(story_bible_id) is not StoryBibleId:
            raise InvalidStoryBibleState
        self.story_bible_id = story_bible_id
        super().__init__()


class StoryBibleForProjectAlreadyExists(StoryBibleRepositoryError):
    """Raised when one Project already owns its allowed Story Bible."""

    code = "story_bible_for_project_already_exists"
    message = "The Project already has a Story Bible."

    def __init__(self, project_id: ProjectId) -> None:
        if type(project_id) is not ProjectId:
            raise InvalidStoryBibleState
        self.project_id = project_id
        super().__init__()


class StoryBibleProjectNotFound(StoryBibleRepositoryError):
    """Raised when persistence cannot find the required owning Project."""

    code = "story_bible_project_not_found"
    message = "The owning Project was not found."

    def __init__(self, project_id: ProjectId) -> None:
        if type(project_id) is not ProjectId:
            raise InvalidStoryBibleState
        self.project_id = project_id
        super().__init__()


class StoryBibleNotFound(StoryBibleRepositoryError):
    """Raised when a requested Story Bible cannot be found for a write."""

    code = "story_bible_not_found"
    message = "The Story Bible was not found."

    def __init__(self, story_bible_id: StoryBibleId) -> None:
        if type(story_bible_id) is not StoryBibleId:
            raise InvalidStoryBibleState
        self.story_bible_id = story_bible_id
        super().__init__()


class StoryBibleDataCorruption(StoryBibleRepositoryError):
    """Raised when stored rows cannot form one valid current aggregate."""

    code = "story_bible_data_corruption"
    message = "The stored Story Bible state is inconsistent."

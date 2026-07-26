"""Safe framework-independent failures owned by the Story Bible domain."""

from aiwebnovel.domain.errors import DomainError


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

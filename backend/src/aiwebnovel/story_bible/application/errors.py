"""Safe failures that exist only at the Story Bible application boundary."""

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.identifiers import StoryBibleId


class StoryBibleForProjectNotFound(DomainError):
    """Report that an existing Project has no Story Bible."""

    code = "story_bible_for_project_not_found"
    message = "The Project does not have a Story Bible."

    def __init__(self, project_id: ProjectId) -> None:
        if type(project_id) is not ProjectId:
            raise TypeError("project_id must be a ProjectId")
        self.project_id = project_id
        super().__init__()


class StoryBibleRevisionNotFound(DomainError):
    """Report that one Story Bible exists but the requested revision does not."""

    code = "story_bible_revision_not_found"
    message = "The Story Bible revision was not found."

    def __init__(
        self,
        story_bible_id: StoryBibleId,
        revision_number: RevisionNumber,
    ) -> None:
        if type(story_bible_id) is not StoryBibleId or type(revision_number) is not RevisionNumber:
            raise TypeError("story_bible_id and revision_number must be exact domain values")
        self.story_bible_id = story_bible_id
        self.revision_number = revision_number
        super().__init__()


__all__ = ["StoryBibleForProjectNotFound", "StoryBibleRevisionNotFound"]

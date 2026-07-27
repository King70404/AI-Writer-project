"""Safe failures that exist only at the Story Bible application boundary."""

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.project.identifiers import ProjectId


class StoryBibleForProjectNotFound(DomainError):
    """Report that an existing Project has no Story Bible."""

    code = "story_bible_for_project_not_found"
    message = "The Project does not have a Story Bible."

    def __init__(self, project_id: ProjectId) -> None:
        if type(project_id) is not ProjectId:
            raise TypeError("project_id must be a ProjectId")
        self.project_id = project_id
        super().__init__()


__all__ = ["StoryBibleForProjectNotFound"]

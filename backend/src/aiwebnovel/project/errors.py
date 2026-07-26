"""Safe framework-independent failures owned by the Project domain."""

from aiwebnovel.domain.errors import DomainError as DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId


class ProjectDomainError(DomainError):
    """Base class for expected Project domain failures."""

    code = "project_domain_error"
    message = "The Project domain operation could not be completed."


class InvalidProjectTitle(ProjectDomainError):
    """Raised when a Project title violates its value-object rules."""

    code = "invalid_project_title"
    message = "The Project title is invalid."


class InvalidProjectDescription(ProjectDomainError):
    """Raised when a Project description violates its value-object rules."""

    code = "invalid_project_description"
    message = "The Project description is invalid."


class InvalidProjectState(ProjectDomainError):
    """Raised when Project objects do not form one valid aggregate state."""

    code = "invalid_project_state"
    message = "The Project state is invalid."


class ProjectRevisionConflict(ProjectDomainError):
    """Describe a safe revision-number mismatch without resolving it."""

    code = "project_revision_conflict"
    message = "The expected Project revision does not match the current revision."

    def __init__(self, *, expected_revision_number: int, actual_revision_number: int) -> None:
        if (
            type(expected_revision_number) is not int
            or expected_revision_number < 1
            or type(actual_revision_number) is not int
            or actual_revision_number < 1
        ):
            raise InvalidProjectState
        self.expected_revision_number = expected_revision_number
        self.actual_revision_number = actual_revision_number
        super().__init__()


class ProjectRepositoryError(ProjectDomainError):
    """Base class for safe Project persistence-boundary failures."""

    code = "project_repository_error"
    message = "The Project persistence operation could not be completed."


class ProjectAlreadyExists(ProjectRepositoryError):
    """Raised when create would reuse an existing stable Project identity."""

    code = "project_already_exists"
    message = "The Project already exists."

    def __init__(self, project_id: ProjectId) -> None:
        if type(project_id) is not ProjectId:
            raise InvalidProjectState
        self.project_id = project_id
        super().__init__()


class ProjectNotFound(ProjectRepositoryError):
    """Raised when a requested Project cannot be found for a write."""

    code = "project_not_found"
    message = "The Project was not found."

    def __init__(self, project_id: ProjectId) -> None:
        if type(project_id) is not ProjectId:
            raise InvalidProjectState
        self.project_id = project_id
        super().__init__()


class ProjectRevisionNotFound(ProjectDomainError):
    """Raised when a Project exists but one requested revision does not."""

    code = "project_revision_not_found"
    message = "The Project revision was not found."

    def __init__(
        self,
        project_id: ProjectId,
        revision_number: RevisionNumber,
    ) -> None:
        if type(project_id) is not ProjectId or type(revision_number) is not RevisionNumber:
            raise InvalidProjectState
        self.project_id = project_id
        self.revision_number = revision_number
        super().__init__()


class ProjectPersistenceConflict(ProjectRepositoryError):
    """Raised for a known persistence conflict that is not a stale version."""

    code = "project_persistence_conflict"
    message = "The Project persistence state conflicts with the requested operation."


class ProjectDataCorruption(ProjectRepositoryError):
    """Raised when stored rows cannot form one valid current Project aggregate."""

    code = "project_data_corruption"
    message = "The stored Project state is inconsistent."

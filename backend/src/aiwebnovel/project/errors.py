"""Safe framework-independent failures owned by the Project domain."""

from aiwebnovel.domain.errors import DomainError


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

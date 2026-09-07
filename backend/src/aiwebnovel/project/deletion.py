"""Project logical-deletion markers that reuse immutable revision history."""

from aiwebnovel.project.identifiers import ProjectId

PROJECT_DELETION_TITLE_PREFIX = "__AIWEBNOVEL_DELETED__:"


def deleted_project_title(project_id: ProjectId) -> str:
    """Return the reserved current-revision title used to hide one Project."""
    if type(project_id) is not ProjectId:
        raise TypeError("project_id must be a ProjectId")
    return f"{PROJECT_DELETION_TITLE_PREFIX}{project_id}"


def is_deleted_project_title(value: object) -> bool:
    """Recognize only canonical reserved tombstone titles."""
    if type(value) is not str or not value.startswith(PROJECT_DELETION_TITLE_PREFIX):
        return False
    raw_project_id = value[len(PROJECT_DELETION_TITLE_PREFIX) :]
    try:
        ProjectId.parse(raw_project_id)
    except Exception:  # Domain parser owns exact validation details.
        return False
    return True


def is_reserved_project_title(value: object) -> bool:
    """Prevent author input from entering the internal tombstone namespace."""
    return type(value) is str and value.startswith(PROJECT_DELETION_TITLE_PREFIX)


__all__ = [
    "PROJECT_DELETION_TITLE_PREFIX",
    "deleted_project_title",
    "is_deleted_project_title",
    "is_reserved_project_title",
]

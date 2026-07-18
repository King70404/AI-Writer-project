"""Public framework-independent Project domain contracts."""

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.entities import Project, ProjectAggregate, ProjectHead, ProjectRevision
from aiwebnovel.project.errors import (
    InvalidProjectDescription,
    InvalidProjectState,
    InvalidProjectTitle,
    ProjectDomainError,
    ProjectRevisionConflict,
)
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.transitions import create_initial_project, create_next_project_revision
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

__all__ = [
    "ConcurrencyVersion",
    "InvalidProjectDescription",
    "InvalidProjectState",
    "InvalidProjectTitle",
    "Project",
    "ProjectAggregate",
    "ProjectDescription",
    "ProjectDomainError",
    "ProjectHead",
    "ProjectId",
    "ProjectRevision",
    "ProjectRevisionConflict",
    "ProjectRevisionId",
    "ProjectTitle",
    "RevisionNumber",
    "create_initial_project",
    "create_next_project_revision",
]

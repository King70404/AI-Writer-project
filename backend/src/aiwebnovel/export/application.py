"""Assemble the current server-saved manuscript through public query services."""

from aiwebnovel.novel_structure.application.queries import (
    GetChapterContentQuery,
    ListChaptersQuery,
    ListVolumesQuery,
)
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId


class ExportProjectManuscript:
    """Read current heads only; never write revisions, files, or candidate state."""

    def __init__(
        self, projects: ProjectQueryService, structure: NovelStructureQueryService
    ) -> None:
        self._projects = projects
        self._structure = structure

    def execute(self, project_id: str) -> str:
        identity = ProjectId.parse(project_id)
        project = self._projects.get_project(GetProjectQuery(project_id=str(identity)))
        if project is None:
            raise ProjectNotFound(identity)
        blocks = [f"《{project.title}》"]
        volumes = self._structure.list_volumes(ListVolumesQuery(project_id=str(identity)))
        for volume in sorted(volumes, key=lambda item: item.position):
            blocks.append(f"第{volume.position}卷 {volume.title}")
            chapters = self._structure.list_chapters(ListChaptersQuery(volume_id=volume.volume_id))
            for chapter in sorted(chapters, key=lambda item: item.position):
                content = self._structure.get_chapter_content(
                    GetChapterContentQuery(chapter_id=chapter.chapter_id)
                )
                blocks.extend((f"第{chapter.position}章 {chapter.title}", content.content))
        return "\n\n".join(blocks) + "\n"

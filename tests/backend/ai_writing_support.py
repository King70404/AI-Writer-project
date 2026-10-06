"""Test-only bounded read spies and generation doubles."""

from types import SimpleNamespace
from unittest.mock import Mock

from tests.backend.novel_structure_repository_support import chapter_id, project_id, volume_id

from aiwebnovel.ai_writing.application.context import ChapterWritingContextBuilder
from aiwebnovel.ai_writing.application.models import GeneratedText, GenerationMessage
from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.novel_structure.errors import OutlineNotFound
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.story_bible.application.errors import StoryBibleForProjectNotFound
from aiwebnovel.story_bible.application.services import StoryBibleQueryService

CHAPTER = str(chapter_id())
PROJECT = str(project_id())
VOLUME = str(volume_id())


class FakeProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[GenerationMessage, ...]] = []
        self.error = error

    def generate(self, messages: tuple[GenerationMessage, ...]) -> GeneratedText:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return GeneratedText("候选正文\n第二段", "test-model")


def sources() -> SimpleNamespace:
    chapter = SimpleNamespace(
        chapter_id=CHAPTER,
        project_id=PROJECT,
        volume_id=VOLUME,
        current_revision_id="revision-1",
        position=3,
        title="当前章",
        summary="当前梗概",
    )
    content = SimpleNamespace(
        content="正文尾部",
        current_revision_id="revision-1",
        project_id=PROJECT,
        volume_id=VOLUME,
    )
    structure = Mock(spec=NovelStructureQueryService)
    structure.get_chapter.return_value = chapter
    structure.get_chapter_content.return_value = content
    structure.get_outline_for_project.side_effect = OutlineNotFound()
    structure.get_volume.return_value = SimpleNamespace(
        project_id=PROJECT,
        title="当前卷",
        summary="卷梗概",
        volume_id=VOLUME,
        current_revision_id="volume-revision",
    )
    structure.list_chapters.return_value = (chapter,)
    projects = Mock(spec=ProjectQueryService)
    projects.get_project.return_value = SimpleNamespace(
        title="项目", description="简介", project_id=PROJECT, current_revision_id="project-revision"
    )
    bibles = Mock(spec=StoryBibleQueryService)
    bibles.get_story_bible_for_project.side_effect = StoryBibleForProjectNotFound(project_id())
    characters = Mock(spec=CharacterQueryService)
    characters.list_characters_for_project.return_value = SimpleNamespace(items=(), has_more=False)
    return SimpleNamespace(
        chapter=chapter,
        content=content,
        structure=structure,
        projects=projects,
        bibles=bibles,
        characters=characters,
        builder=ChapterWritingContextBuilder(structure, projects, bibles, characters),
    )

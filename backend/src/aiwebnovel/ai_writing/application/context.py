"""Bounded current snapshots, read only through public application services."""

from aiwebnovel.ai_writing.application.models import ChapterWritingContext, ContextManifest
from aiwebnovel.ai_writing.errors import AIContextChanged
from aiwebnovel.character.application.queries import ListCharactersForProjectQuery
from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.novel_structure.application.queries import (
    GetChapterContentQuery,
    GetChapterQuery,
    GetOutlineForProjectQuery,
    GetVolumeQuery,
    ListChaptersQuery,
)
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.novel_structure.errors import OutlineNotFound
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.story_bible.application.errors import StoryBibleForProjectNotFound
from aiwebnovel.story_bible.application.queries import GetStoryBibleForProjectQuery
from aiwebnovel.story_bible.application.services import StoryBibleQueryService

CONTEXT_CHARACTER_BUDGET = 60_000
CURRENT_CONTENT_LIMIT = 24_000
PREVIOUS_CONTENT_LIMIT = 8_000
CHARACTER_CONTEXT_LIMIT = 6_000


class _Assembly:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.included: list[str] = []
        self.omitted: list[str] = []
        self.count = 0
        self.truncated = False

    def add(self, source: str, text: str | None, limit: int, *, tail: bool = False) -> None:
        if text is None:
            self.omitted.append(source)
            return
        label = f"\n[{source}]\n"
        available = max(0, min(limit, CONTEXT_CHARACTER_BUDGET - self.count - len(label)))
        if available == 0:
            self.omitted.append(source)
            self.truncated = True
            return
        if len(text) > available:
            self.truncated = True
            text = text[-available:] if tail else text[:available]
        self.parts.append(label + text)
        self.count += len(label) + len(text)
        if source not in self.included:
            self.included.append(source)

    def finish(self) -> ChapterWritingContext:
        return ChapterWritingContext(
            "".join(self.parts),
            ContextManifest(tuple(self.included), tuple(self.omitted), self.truncated, self.count),
        )


class ChapterWritingContextBuilder:
    def __init__(
        self,
        structure: NovelStructureQueryService,
        projects: ProjectQueryService,
        story_bibles: StoryBibleQueryService,
        characters: CharacterQueryService,
    ) -> None:
        self._structure = structure
        self._projects = projects
        self._story_bibles = story_bibles
        self._characters = characters

    def build(self, chapter_id: str) -> ChapterWritingContext:
        chapter = self._structure.get_chapter(GetChapterQuery(chapter_id))
        content = self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))
        if (
            content.current_revision_id != chapter.current_revision_id
            or content.project_id != chapter.project_id
            or content.volume_id != chapter.volume_id
        ):
            raise AIContextChanged
        result = _Assembly()
        result.add(
            "current_chapter",
            f"id={chapter.chapter_id}\nproject={chapter.project_id}\n"
            f"volume={chapter.volume_id}\nposition={chapter.position}\n"
            f"title={chapter.title}\nsummary={chapter.summary}",
            4_000,
        )
        result.add("current_chapter", content.content, CURRENT_CONTENT_LIMIT, tail=True)
        try:
            outline = self._structure.get_outline_for_project(
                GetOutlineForProjectQuery(chapter.project_id)
            )
        except OutlineNotFound:
            result.add("outline", None, 3_000)
        else:
            result.add("outline", f"{outline.title}\n{outline.summary}", 3_000)
        try:
            bible = self._story_bibles.get_story_bible_for_project(
                GetStoryBibleForProjectQuery(chapter.project_id)
            )
        except StoryBibleForProjectNotFound:
            result.add("story_bible", None, 16_000)
        else:
            result.add("story_bible", f"{bible.title}\n{bible.content}", 16_000)
        volume = self._structure.get_volume(GetVolumeQuery(chapter.volume_id))
        if volume.project_id != chapter.project_id:
            raise AIContextChanged
        result.add("volume", f"{volume.title}\n{volume.summary}", 3_000)
        earlier = tuple(
            item
            for item in self._structure.list_chapters(ListChaptersQuery(chapter.volume_id))
            if item.position < chapter.position
            and item.volume_id == chapter.volume_id
            and item.project_id == chapter.project_id
        )
        if earlier:
            previous = max(earlier, key=lambda item: item.position)
            previous_content = self._structure.get_chapter_content(
                GetChapterContentQuery(previous.chapter_id)
            )
            if previous_content.current_revision_id != previous.current_revision_id:
                raise AIContextChanged
            result.add("previous_chapter", f"{previous.title}\n{previous.summary}", 3_000)
            result.add(
                "previous_chapter", previous_content.content, PREVIOUS_CONTENT_LIMIT, tail=True
            )
        else:
            result.add("previous_chapter", None, PREVIOUS_CONTENT_LIMIT)
        page = self._characters.list_characters_for_project(
            ListCharactersForProjectQuery(chapter.project_id, limit=100)
        )
        # Existing list order is stable created_at/id descending; never fetch profiles/history.
        result.add(
            "characters",
            "\n".join(f"{item.name}: {item.role}" for item in page.items) if page.items else None,
            CHARACTER_CONTEXT_LIMIT,
        )
        result.truncated |= page.has_more
        project = self._projects.get_project(GetProjectQuery(chapter.project_id))
        result.add("project", f"{project.title}\n{project.description}" if project else None, 3_000)
        return result.finish()

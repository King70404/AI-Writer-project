"""Resolve only author-selected assets; keep source identities in the model preview."""

from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

from aiwebnovel.ai_writing.application.models import ContextSource
from aiwebnovel.ai_writing.errors import AIContextChanged
from aiwebnovel.chapter_planning.models import (
    ChapterPlan,
    ChapterPlanDocument,
    PlanningReferenceInvalid,
    SaveChapterPlan,
)
from aiwebnovel.character.application.queries import GetCharacterQuery
from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.novel_structure.application.queries import GetChapterQuery
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.story_bible.application.queries import GetStoryBibleForProjectQuery
from aiwebnovel.story_bible.application.services import StoryBibleQueryService

RuleValidator = Callable[[str, tuple[str, ...]], object]
RuleSources = Callable[[str, tuple[str, ...]], tuple[ContextSource, ...]]


class PlanningRepository(Protocol):
    def get(self, chapter_id: str) -> ChapterPlan | None: ...

    def save(self, chapter_id: str, document: SaveChapterPlan) -> ChapterPlan: ...


class ChapterPlanningService:
    def __init__(
        self,
        repository: PlanningRepository,
        structure: NovelStructureQueryService,
        characters: CharacterQueryService,
        story_bibles: StoryBibleQueryService,
        validate_rule_revisions: RuleValidator,
        snapshot_rules: RuleSources,
    ) -> None:
        self._repository = repository
        self._structure = structure
        self._characters = characters
        self._story_bibles = story_bibles
        self._validate_rule_revisions = validate_rule_revisions
        self._snapshot_rules = snapshot_rules

    def get(self, chapter_id: str) -> ChapterPlan | None:
        return self._repository.get(chapter_id)

    def save(self, chapter_id: str, document: SaveChapterPlan) -> ChapterPlan:
        # The planning repository also checks soft-deleted project ownership. The
        # structure snapshot supplies chapter metadata, not that visibility check.
        self.get(chapter_id)
        chapter = self._structure.get_chapter(GetChapterQuery(chapter_id))
        try:
            self._asset_sources(chapter.project_id, document)
            self._validate_rule_revisions(
                chapter.project_id, tuple(document.writing_rule_revision_ids)
            )
        except DomainError:
            raise PlanningReferenceInvalid from None
        return self._repository.save(chapter_id, document)

    def _asset_sources(
        self, project_id: str, document: ChapterPlanDocument
    ) -> tuple[ContextSource, ...]:
        sources: list[ContextSource] = []
        character_ids = dict.fromkeys(
            identifier for scene in document.scenes for identifier in scene.character_ids
        )
        for identifier in character_ids:
            character = self._characters.get_character(GetCharacterQuery(identifier))
            if character.project_id != project_id:
                raise PlanningReferenceInvalid
            sources.append(
                ContextSource(
                    "planning_assets",
                    ((character.character_id, character.current_revision_id),),
                    f"人物: {character.name}\n角色: {character.role}\n{character.profile}",
                    "章节场景明确关联的人物当前版本",
                    None,
                    False,
                )
            )
        if document.include_story_bible:
            bible = self._story_bibles.get_story_bible_for_project(
                GetStoryBibleForProjectQuery(project_id)
            )
            sources.append(
                ContextSource(
                    "planning_assets",
                    ((bible.story_bible_id, bible.current_revision_id),),
                    f"设定: {bible.title}\n{bible.content}",
                    "作者选择关联的小说设定当前版本",
                    None,
                    False,
                )
            )
        remaining = 12_000
        bounded = []
        for source in sources:
            text = source.text[:remaining]
            bounded.append(
                replace(
                    source,
                    text=text,
                    truncated=len(text) != len(source.text),
                    omitted_reason="章节关联资料预算已用完" if not text else None,
                )
            )
            remaining -= len(text)
        return tuple(bounded)

    def context_sources(self, chapter_id: str) -> tuple[ContextSource, ...]:
        plan = self.get(chapter_id)
        if plan is None:
            return ()
        document = ChapterPlanDocument.model_validate(
            plan.model_dump(
                exclude={"chapter_id", "project_id", "version", "revision_id", "updated_at"}
            )
        )
        source = ContextSource(
            "chapter_plan",
            ((chapter_id, plan.revision_id),),
            document.model_dump_json(),
            "作者已保存的章节重点、目标字数、冲突、场景与情节推进顺序",
            None,
            False,
        )
        try:
            sources = (
                source,
                *self._asset_sources(plan.project_id, document),
                *self._snapshot_rules(plan.project_id, tuple(plan.writing_rule_revision_ids)),
            )
        except DomainError:
            raise AIContextChanged from None
        current = self.get(chapter_id)
        if current is None or current.revision_id != plan.revision_id:
            raise AIContextChanged
        return sources

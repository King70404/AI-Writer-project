"""Deterministic, bounded, read-only context assembly."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest
from tests.backend.ai_writing_support import CHAPTER, PROJECT, VOLUME, sources

from aiwebnovel.ai_writing.application.context import (
    CONTEXT_CHARACTER_BUDGET,
    CURRENT_CONTENT_LIMIT,
    _Assembly,
)
from aiwebnovel.ai_writing.errors import AIContextChanged


def test_minimal_context_optional_omissions_and_read_only_calls() -> None:
    s = sources()
    result = s.builder.build(CHAPTER)
    assert result.manifest.included_sources == ("current_chapter", "volume", "project")
    assert result.manifest.omitted_sources == (
        "outline",
        "story_bible",
        "previous_chapter",
        "characters",
    )
    assert result.manifest.character_count == len(result.text)
    assert not result.manifest.truncated
    assert "正文尾部" in result.text
    for service in (s.structure, s.projects, s.bibles, s.characters):
        assert all(call[0].startswith(("get_", "list_")) for call in service.mock_calls)
    with pytest.raises(FrozenInstanceError):
        result.text = "changed"


def test_all_sources_previous_nearest_same_volume_and_stable_character_order() -> None:
    s = sources()
    s.structure.get_outline_for_project.side_effect = None
    s.structure.get_outline_for_project.return_value = SimpleNamespace(
        title="大纲", summary="大纲梗概"
    )
    s.bibles.get_story_bible_for_project.side_effect = None
    s.bibles.get_story_bible_for_project.return_value = SimpleNamespace(
        title="设定", content="设定内容"
    )
    previous = SimpleNamespace(
        chapter_id="previous",
        project_id=PROJECT,
        volume_id=VOLUME,
        position=2,
        title="上一章",
        summary="上一章梗概",
        current_revision_id="prev",
    )
    earlier = SimpleNamespace(**{**vars(previous), "chapter_id": "earlier", "position": 1})
    foreign = SimpleNamespace(**{**vars(previous), "volume_id": "foreign"})
    foreign_project = SimpleNamespace(**{**vars(previous), "project_id": "foreign"})
    s.structure.list_chapters.return_value = (
        foreign,
        s.chapter,
        previous,
        earlier,
        foreign_project,
    )
    s.structure.get_chapter_content.side_effect = [
        s.content,
        SimpleNamespace(content="前" * 9000 + "末尾", current_revision_id="prev"),
    ]
    s.characters.list_characters_for_project.return_value = SimpleNamespace(
        items=(SimpleNamespace(name="乙", role="配角"), SimpleNamespace(name="甲", role="主角")),
        has_more=False,
    )
    result = s.builder.build(CHAPTER)
    assert result.manifest.included_sources == (
        "current_chapter",
        "outline",
        "story_bible",
        "volume",
        "previous_chapter",
        "characters",
        "project",
    )
    assert result.manifest.omitted_sources == ()
    assert result.manifest.truncated
    assert s.structure.get_chapter_content.call_args.args[0].chapter_id == "previous"
    assert "上一章梗概" in result.text and "末尾" in result.text
    assert result.text.index("乙: 配角") < result.text.index("甲: 主角")
    assert s.characters.list_characters_for_project.call_args.args[0].limit == 100


def test_budget_tail_priority_determinism_and_character_cap() -> None:
    s = sources()
    s.content.content = "开头" + "文" * 30_000 + "结尾"
    s.structure.get_outline_for_project.side_effect = None
    s.structure.get_outline_for_project.return_value = SimpleNamespace(
        title="纲", summary="纲" * 9000
    )
    s.bibles.get_story_bible_for_project.side_effect = None
    s.bibles.get_story_bible_for_project.return_value = SimpleNamespace(
        title="设", content="设" * 50000
    )
    s.characters.list_characters_for_project.return_value = SimpleNamespace(
        items=tuple(SimpleNamespace(name="角", role="角" * 500) for _ in range(100)), has_more=True
    )
    first = s.builder.build(CHAPTER)
    second = s.builder.build(CHAPTER)
    assert first == second
    assert first.manifest.truncated
    assert first.manifest.character_count == len(first.text) <= CONTEXT_CHARACTER_BUDGET
    assert "开头" not in first.text and "结尾" in first.text
    assert first.text.count("文") == CURRENT_CONTENT_LIMIT - 2
    assert first.text.count("角") <= 6000


def test_global_budget_records_omissions_without_exceeding_count() -> None:
    a = _Assembly()
    a.add("current_chapter", "x" * 70000, 70000, tail=True)
    a.add("characters", "later", 6000)
    result = a.finish()
    assert len(result.text) == CONTEXT_CHARACTER_BUDGET
    assert result.manifest.truncated and result.manifest.omitted_sources == ("characters",)


@pytest.mark.parametrize("field", ["current_revision_id", "project_id", "volume_id"])
def test_mixed_current_revision_or_ownership_fails_before_other_reads(field: str) -> None:
    s = sources()
    setattr(s.content, field, "changed")
    with pytest.raises(AIContextChanged):
        s.builder.build(CHAPTER)
    s.bibles.get_story_bible_for_project.assert_not_called()


def test_volume_ownership_and_previous_revision_races() -> None:
    s = sources()
    s.structure.get_volume.return_value.project_id = "foreign"
    with pytest.raises(AIContextChanged):
        s.builder.build(CHAPTER)
    s = sources()
    s.structure.list_chapters.return_value = (
        SimpleNamespace(**{**vars(s.chapter), "position": 1}),
    )
    s.structure.get_chapter_content.side_effect = [
        s.content,
        SimpleNamespace(current_revision_id="changed"),
    ]
    with pytest.raises(AIContextChanged):
        s.builder.build(CHAPTER)


def test_absent_project_is_explicitly_omitted() -> None:
    s = sources()
    s.projects.get_project.return_value = None
    result = s.builder.build(CHAPTER)
    assert "project" in result.manifest.omitted_sources

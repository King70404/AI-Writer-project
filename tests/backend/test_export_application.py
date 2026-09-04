"""Deterministic formatting and public-query-only manuscript export."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.export.application import ExportProjectManuscript
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.errors import ProjectNotFound

PROJECT_ID = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def test_export_sorts_both_levels_and_reads_only_current_content() -> None:
    projects = Mock(spec=ProjectQueryService)
    structure = Mock(spec=NovelStructureQueryService)
    projects.get_project.return_value = SimpleNamespace(title="归途")
    structure.list_volumes.return_value = (
        SimpleNamespace(position=2, title="空卷", volume_id="second"),
        SimpleNamespace(position=1, title="初见", volume_id="first"),
    )
    structure.list_chapters.side_effect = [
        (
            SimpleNamespace(position=2, title="空章", chapter_id="second"),
            SimpleNamespace(position=1, title="雨夜", chapter_id="first"),
        ),
        (),
    ]
    structure.get_chapter_content.side_effect = [
        SimpleNamespace(content="雨落长街。\n灯还亮着。"),
        SimpleNamespace(content=""),
    ]
    result = ExportProjectManuscript(projects, structure).execute(PROJECT_ID)
    assert (
        result
        == "《归途》\n\n第1卷 初见\n\n第1章 雨夜\n\n雨落长街。\n灯还亮着。\n\n第2章 空章\n\n\n\n第2卷 空卷\n"
    )
    assert projects.get_project.call_count == 1
    assert structure.list_volumes.call_count == 1
    assert [call.args[0].volume_id for call in structure.list_chapters.call_args_list] == [
        "first",
        "second",
    ]
    assert [call.args[0].chapter_id for call in structure.get_chapter_content.call_args_list] == [
        "first",
        "second",
    ]
    assert {call[0] for call in structure.mock_calls} == {
        "list_volumes",
        "list_chapters",
        "get_chapter_content",
    }


def test_no_volumes_exports_only_project_title() -> None:
    projects = Mock(spec=ProjectQueryService)
    structure = Mock(spec=NovelStructureQueryService)
    projects.get_project.return_value = SimpleNamespace(title="空项目")
    structure.list_volumes.return_value = ()
    assert ExportProjectManuscript(projects, structure).execute(PROJECT_ID) == "《空项目》\n"
    structure.list_chapters.assert_not_called()


def test_missing_project_stops_before_structure_queries() -> None:
    projects = Mock(spec=ProjectQueryService)
    structure = Mock(spec=NovelStructureQueryService)
    projects.get_project.return_value = None
    with pytest.raises(ProjectNotFound):
        ExportProjectManuscript(projects, structure).execute(PROJECT_ID)
    assert structure.mock_calls == []


@pytest.mark.parametrize("project_id", ["", "invalid", PROJECT_ID.upper()])
def test_invalid_identifier_has_no_query_side_effect(project_id: str) -> None:
    projects = Mock(spec=ProjectQueryService)
    structure = Mock(spec=NovelStructureQueryService)
    with pytest.raises(InvalidDomainIdentifier):
        ExportProjectManuscript(projects, structure).execute(project_id)
    assert projects.mock_calls == structure.mock_calls == []

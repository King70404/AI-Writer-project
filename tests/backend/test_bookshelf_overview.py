"""Bookshelf aggregates use persisted metadata and a bounded number of SQL queries."""

import pytest
from sqlalchemy import event
from tests.backend.test_ai_workflow import workflow
from tests.backend.test_workbench import editorial, save_content, summary

__all__ = ["workflow"]


def overview(w, **params):
    result = w.client.get("/api/v1/workspace/overview", params=params)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()


def test_multi_book_totals_match_single_workspace_with_constant_queries(workflow):
    w = workflow
    save_content(w, w.chapter, "风\t 雨😀\u3000" * 10000)
    assert editorial(w, "review", 0).status_code == 200
    for number in range(4):
        created = w.client.post(
            "/api/v1/projects",
            headers=w.headers,
            json={"title": f"空书{number}", "description": ""},
        )
        assert created.status_code == 201
    repository = w.app.state.workbench_service._repository
    with repository._sessions() as session:
        engine = session.get_bind()
    queries = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        first = overview(w, limit=1)
        first_count = len(queries)
        queries.clear()
        all_books = overview(w, limit=100)
        assert len(queries) == first_count == 9
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert all_books["total"] == 5 and len(all_books["items"]) == 5
    assert first["next_offset"] == 1
    for book in all_books["items"]:
        single = summary(w, book["project_id"])
        for name in ("characters", "chapter_count", "volume_count", "editorial", "action_total"):
            assert book[name] == single[name]
        assert set(book) == {
            "project_id",
            "title",
            "characters",
            "chapter_count",
            "volume_count",
            "editorial",
            "action_total",
        }
    own = next(book for book in all_books["items"] if book["project_id"] == w.project)
    assert own["characters"] == 30000
    assert own["editorial"] == {"draft": 0, "review": 1, "final": 0}
    assert overview(w, offset=999)["items"] == []


@pytest.mark.parametrize("query", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"unknown": 1}])
def test_overview_page_bounds(workflow, query):
    assert workflow.client.get("/api/v1/workspace/overview", params=query).status_code == 422


def test_deleted_book_is_excluded_and_empty_page_has_no_invented_statistics(workflow):
    w = workflow
    project = w.client.get(f"/api/v1/projects/{w.project}")
    deleted = w.client.post(
        f"/api/v1/projects/{w.project}/delete",
        headers={**w.headers, "If-Match": project.headers["etag"]},
    )
    assert deleted.status_code == 200
    result = overview(w)
    assert result["total"] == 0 and result["items"] == [] and result["next_offset"] is None


def test_long_book_counts_saved_text_without_returning_manuscript(workflow):
    from tests.backend.test_workbench import add_chapter

    w = workflow
    volume = w.client.get(w.base + "/content").json()["volume_id"]
    original = summary(w)["characters"]
    for number in range(12):
        add_chapter(w, volume, f"长章{number}", number + 2, "文" * 100000)
    result = overview(w)
    assert result["items"][0]["characters"] == original + 1200000
    assert result["items"][0]["chapter_count"] == 13
    assert len(str(result)) < 2000
    assert w.calls == []


def test_unavailable_workbench_returns_no_fabricated_statistics(workflow):
    w = workflow
    service = w.app.state.workbench_service
    try:
        w.app.state.workbench_service = None
        result = w.client.get("/api/v1/workspace/overview")
        assert result.status_code == 200 and result.json() is None
        assert result.headers["cache-control"] == "no-store"
        w.app.state.workbench_service = service
        w.app.state.ai_workflow_schema_required = True
        assert w.client.get("/api/v1/workspace/overview").json() is None
    finally:
        w.app.state.workbench_service = service
        w.app.state.ai_workflow_schema_required = False

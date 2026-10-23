"""Derive workbench totals and one de-duplicated to-do list from persisted state only.

No method here calls a model provider, changes manuscript text, or confirms facts.
Each to-do item is one (kind, chapter) pair; a fact that is both pending and stale is
counted once as stale, so the same problem never appears under two headings.
"""

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.workbench.models import (
    ACTION_ORDER,
    ActionCount,
    ActionItem,
    ActionKind,
    ActionPage,
    ChapterSummary,
    ChapterSummaryPage,
    EditorialCounts,
    EditorialState,
    EditorialStatus,
    LatestChapter,
    VolumeSummary,
    WorkspaceSummary,
)
from aiwebnovel.workbench.snapshot import ChapterRow, MemoryRow, ProjectSnapshot


class WorkbenchVolumeNotFound(DomainError):
    message = "The volume does not belong to this project."


class WorkbenchRepository(Protocol):
    def snapshot(self, project_id: str) -> ProjectSnapshot: ...

    def get_editorial(self, chapter_id: str) -> EditorialState: ...

    def save_editorial(
        self, chapter_id: str, status: EditorialStatus, expected_version: int
    ) -> EditorialState: ...


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _review_stale(
    review: MemoryRow,
    revisions: dict[str, str],
    facts: dict[str, tuple[MemoryRow, bool]],
    order: dict[str, int],
) -> bool:
    """Mirror the story-memory staleness rule without reading review content."""
    if revisions.get(review.chapter_id) != review.source_revision:
        return True
    for reference in review.facts:
        current = facts.get(reference.fact_id)
        if (
            current is None
            or current[0].revision_id != reference.revision_id
            or current[1]
            or current[0].status != "confirmed"
            or order.get(reference.chapter_id, len(order)) >= order.get(review.chapter_id, 0)
        ):
            return True
    return False


def derive_actions(snapshot: ProjectSnapshot) -> list[ActionItem]:
    chapters = {chapter.chapter_id: chapter for chapter in snapshot.chapters}
    order = {chapter.chapter_id: index for index, chapter in enumerate(snapshot.chapters)}
    revisions = {chapter.chapter_id: chapter.revision_id for chapter in snapshot.chapters}
    counts: Counter[tuple[ActionKind, str]] = Counter()
    for chapter_id, count in snapshot.pending_candidates.items():
        counts["pending_candidate", chapter_id] += count
    facts: dict[str, tuple[MemoryRow, bool]] = {}
    latest_reviews: dict[str, MemoryRow] = {}
    for item in snapshot.memory:
        if item.kind == "fact":
            stale = revisions.get(item.chapter_id) != item.source_revision
            facts[item.entity_id] = (item, stale)
            if item.status == "rejected":
                continue
            if stale:
                counts["stale_fact", item.chapter_id] += 1
            elif item.status == "pending":
                counts["pending_fact", item.chapter_id] += 1
        else:
            previous = latest_reviews.get(item.chapter_id)
            if previous is None or (item.updated_at, item.entity_id) > (
                previous.updated_at,
                previous.entity_id,
            ):
                latest_reviews[item.chapter_id] = item
    for review in latest_reviews.values():
        if review.status == "running":
            continue
        if _review_stale(review, revisions, facts, order):
            counts["stale_review", review.chapter_id] += 1
        elif review.status in ("ready", "failed"):
            counts["unfinished_review", review.chapter_id] += 1
    for chapter_id, editorial in snapshot.editorial.items():
        chapter = chapters.get(chapter_id)
        if (
            chapter is not None
            and editorial.status == "final"
            and editorial.chapter_revision_id != chapter.revision_id
        ):
            counts["final_changed", chapter_id] += 1
    rank = {kind: index for index, kind in enumerate(ACTION_ORDER)}
    items = [
        ActionItem(
            kind=kind,
            chapter_id=chapter_id,
            volume_id=chapters[chapter_id].volume_id,
            chapter_title=chapters[chapter_id].title,
            chapter_position=chapters[chapter_id].position,
            volume_position=chapters[chapter_id].volume_position,
            count=count,
        )
        for (kind, chapter_id), count in counts.items()
        if chapter_id in chapters
    ]
    items.sort(key=lambda item: (rank[item.kind], order[item.chapter_id]))
    return items


def _editorial_counts(
    chapters: tuple[ChapterRow, ...] | list[ChapterRow], snapshot: ProjectSnapshot
) -> EditorialCounts:
    statuses = Counter(
        snapshot.editorial[chapter.chapter_id].status
        if chapter.chapter_id in snapshot.editorial
        else "draft"
        for chapter in chapters
    )
    return EditorialCounts(
        draft=statuses["draft"], review=statuses["review"], final=statuses["final"]
    )


def _page[T](items: list[T], offset: int, limit: int) -> tuple[list[T], int | None]:
    page = items[offset : offset + limit]
    end = offset + len(page)
    return page, end if end < len(items) else None


class WorkbenchService:
    def __init__(self, repository: WorkbenchRepository, clock: Callable[[], str] = _now) -> None:
        self._repository = repository
        self._clock = clock

    def summary(self, project_id: str) -> WorkspaceSummary:
        snapshot = self._repository.snapshot(project_id)
        actions = derive_actions(snapshot)
        latest = max(
            snapshot.chapters,
            key=lambda chapter: (chapter.updated_at, chapter.chapter_id),
            default=None,
        )
        volumes = []
        for volume in snapshot.volumes:
            members = [c for c in snapshot.chapters if c.volume_id == volume.volume_id]
            volumes.append(
                VolumeSummary(
                    volume_id=volume.volume_id,
                    title=volume.title,
                    position=volume.position,
                    chapter_count=len(members),
                    characters=sum(chapter.characters for chapter in members),
                    editorial=_editorial_counts(members, snapshot),
                )
            )
        return WorkspaceSummary(
            project_id=project_id,
            characters=sum(chapter.characters for chapter in snapshot.chapters),
            chapter_count=len(snapshot.chapters),
            volume_count=len(snapshot.volumes),
            editorial=_editorial_counts(snapshot.chapters, snapshot),
            latest_chapter=None
            if latest is None
            else LatestChapter(
                chapter_id=latest.chapter_id,
                volume_id=latest.volume_id,
                title=latest.title,
                position=latest.position,
                updated_at=latest.updated_at,
            ),
            volumes=volumes,
            actions=[
                ActionCount(
                    kind=kind,
                    items=sum(item.count for item in actions if item.kind == kind),
                    chapters=sum(1 for item in actions if item.kind == kind),
                )
                for kind in ACTION_ORDER
            ],
            action_total=sum(item.count for item in actions),
            generated_at=self._clock(),
        )

    def chapters(
        self, project_id: str, volume_id: str | None, offset: int, limit: int
    ) -> ChapterSummaryPage:
        snapshot = self._repository.snapshot(project_id)
        if volume_id is not None and all(v.volume_id != volume_id for v in snapshot.volumes):
            raise WorkbenchVolumeNotFound
        open_actions: Counter[str] = Counter()
        for item in derive_actions(snapshot):
            open_actions[item.chapter_id] += item.count
        selected = [
            chapter
            for chapter in snapshot.chapters
            if volume_id is None or chapter.volume_id == volume_id
        ]
        page, next_offset = _page(selected, offset, limit)
        items = []
        for chapter in page:
            editorial = snapshot.editorial.get(chapter.chapter_id)
            items.append(
                ChapterSummary(
                    chapter_id=chapter.chapter_id,
                    volume_id=chapter.volume_id,
                    title=chapter.title,
                    position=chapter.position,
                    characters=chapter.characters,
                    updated_at=chapter.updated_at,
                    editorial_status="draft" if editorial is None else editorial.status,
                    editorial_version=0 if editorial is None else editorial.version,
                    content_changed_since_editorial=editorial is not None
                    and editorial.chapter_revision_id != chapter.revision_id,
                    open_actions=open_actions[chapter.chapter_id],
                )
            )
        return ChapterSummaryPage(
            project_id=project_id,
            volume_id=volume_id,
            total=len(selected),
            offset=offset,
            limit=limit,
            next_offset=next_offset,
            items=items,
        )

    def actions(self, project_id: str, offset: int, limit: int) -> ActionPage:
        actions = derive_actions(self._repository.snapshot(project_id))
        page, next_offset = _page(actions, offset, limit)
        return ActionPage(
            project_id=project_id,
            total=len(actions),
            offset=offset,
            limit=limit,
            next_offset=next_offset,
            items=page,
        )

    def _with_open_actions(self, state: EditorialState) -> EditorialState:
        open_actions = sum(
            item.count
            for item in derive_actions(self._repository.snapshot(state.project_id))
            if item.chapter_id == state.chapter_id and item.kind != "final_changed"
        )
        return state.model_copy(update={"open_actions": open_actions})

    def editorial_state(self, chapter_id: str) -> EditorialState:
        return self._with_open_actions(self._repository.get_editorial(chapter_id))

    def save_editorial_state(
        self, chapter_id: str, status: EditorialStatus, expected_version: int
    ) -> EditorialState:
        return self._with_open_actions(
            self._repository.save_editorial(chapter_id, status, expected_version)
        )

"""Derive reminders from saved thread plans, evidence revisions and budget spend."""

from aiwebnovel.workbench.models import ActionItem
from aiwebnovel.workbench.snapshot import ProjectSnapshot


def reminder_actions(snapshot: ProjectSnapshot) -> list[ActionItem]:
    chapters = {chapter.chapter_id: chapter for chapter in snapshot.chapters}
    result = []
    for thread in snapshot.threads:
        if thread.status == "abandoned":
            continue
        target = chapters.get(thread.payoff_chapter_id or "")
        if target is None and thread.payoff_volume_id:
            target = next(
                (
                    chapter
                    for chapter in reversed(snapshot.chapters)
                    if chapter.volume_id == thread.payoff_volume_id
                ),
                None,
            )
        stale = any(
            chapters.get(chapter_id) is None or chapters[chapter_id].revision_id != revision
            for chapter_id, revision in thread.anchors
        )
        if not stale and not (
            thread.status in {"planned", "planted", "advancing"}
            and target is not None
            and target.characters > 0
        ):
            continue
        result.append(
            ActionItem(
                kind="due_thread",
                chapter_id=None if target is None else target.chapter_id,
                volume_id=None if target is None else target.volume_id,
                chapter_title=thread.title,
                chapter_position=0 if target is None else target.position,
                volume_position=0 if target is None else target.volume_position,
                count=1,
                entity_id=thread.entity_id,
                target_kind="thread",
            )
        )
    budget = snapshot.budget
    if budget is not None and budget.mode != "off":
        unknown = not budget.spend.bounded
        near = (
            budget.monthly_limit is not None
            and budget.spend.upper_micros * 5 >= budget.monthly_limit * 4
        )
        if unknown or near:
            title = (
                "本月存在未计价或不同币种用量，请核对预算"
                if unknown
                else "本月预算已达到或超过 80%，请核对余量"
            )
            result.append(
                ActionItem(
                    kind="budget_reminder",
                    chapter_id=None,
                    volume_id=None,
                    chapter_title=title,
                    chapter_position=0,
                    volume_position=0,
                    count=1,
                    entity_id="monthly-budget",
                    target_kind="budget",
                )
            )
    return result

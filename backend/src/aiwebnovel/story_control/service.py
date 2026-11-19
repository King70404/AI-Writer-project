"""Author-owned plans, plot threads, timeline and recall policy; zero model requests.

Plans and plot threads are guidance the author enters. Evidence is accepted only when its
quote appears in the chapter's current saved revision; later manuscript edits mark it for
review instead of rewriting it. Relations are checked for cycles inside the writer lock.
"""

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import uuid4

from aiwebnovel.ai_writing.application.models import ContextSource
from aiwebnovel.character.application import MAX_CHARACTER_LIST_LIMIT
from aiwebnovel.character.application.queries import (
    GetCharacterQuery,
    ListCharactersForProjectQuery,
)
from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.novel_structure.application.models import ChapterSnapshot
from aiwebnovel.novel_structure.application.queries import (
    GetChapterContentQuery,
    GetChapterQuery,
    ListChaptersQuery,
    ListVolumesQuery,
)
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.story_control.models import (
    MAX_EVENTS,
    MAX_GOALS,
    MAX_STATES,
    MAX_THREADS,
    RECALL_CHARACTER_LIMIT,
    RECALL_ITEM_LIMIT,
    AnchorView,
    ArcPlan,
    ChapterGuide,
    ChapterOption,
    CharacterOption,
    ControlItem,
    Event,
    EventView,
    FactHit,
    FactSearchPage,
    Goal,
    GoalLink,
    GoalView,
    LinkView,
    RecallChoice,
    RecallOmission,
    RecallPolicy,
    RecallPolicyDocument,
    RecallPreview,
    SaveEvent,
    SaveGoal,
    SaveRecallPolicy,
    SaveState,
    SaveThread,
    State,
    StateView,
    StoryControlConflict,
    StoryControlCycle,
    StoryControlInvalid,
    StoryControlNotFound,
    Thread,
    ThreadStatus,
    ThreadView,
    Timeline,
    TimelineWarning,
    VolumeOption,
)
from aiwebnovel.story_memory.models import Fact, RecallSelectionPolicy
from aiwebnovel.story_memory.service import StoryMemoryService

if TYPE_CHECKING:
    from aiwebnovel.story_control.foreshadow import ForeshadowExtractionService
    from aiwebnovel.story_control.proposals import PlanProposalService
    from aiwebnovel.story_control.timeline_extraction import TimelineExtractionService

GUIDE_CHARACTER_LIMIT = 4_000
MAX_CHARACTER_OPTIONS = 500
OPEN_THREAD_STATUSES: frozenset[ThreadStatus] = frozenset({"planned", "planted", "advancing"})


class StoryControlRepository(Protocol):
    def list(self, project_id: str) -> tuple[ControlItem, ...]: ...

    def save(
        self,
        item: ControlItem,
        expected_version: int,
        validate: Callable[[tuple[ControlItem, ...]], None],
    ) -> ControlItem: ...


@dataclass(frozen=True, slots=True)
class Layout:
    project_id: str
    volume_ids: tuple[str, ...]
    chapters: tuple[ChapterSnapshot, ...]

    def chapter(self, chapter_id: str | None) -> ChapterSnapshot | None:
        return next((item for item in self.chapters if item.chapter_id == chapter_id), None)

    def index(self, chapter_id: str) -> int:
        return next(i for i, item in enumerate(self.chapters) if item.chapter_id == chapter_id)

    def volume_position(self, volume_id: str) -> int:
        return self.volume_ids.index(volume_id) + 1


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _has_text(text: str) -> bool:
    return any(not character.isspace() for character in text)


def _reachable(edges: dict[str, set[str]], start: str, target: str) -> bool:
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for following in edges.get(node, ()):
            if following == target:
                return True
            if following not in seen:
                seen.add(following)
                queue.append(following)
    return False


def _has_cycle(edges: dict[str, set[str]]) -> bool:
    nodes = set(edges) | {node for targets in edges.values() for node in targets}
    incoming = dict.fromkeys(nodes, 0)
    for targets in edges.values():
        for node in targets:
            incoming[node] += 1
    queue = deque(node for node, count in incoming.items() if count == 0)
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for following in edges.get(node, ()):
            incoming[following] -= 1
            if incoming[following] == 0:
                queue.append(following)
    return visited != len(nodes)


def _event_edges(events: Iterable[Event]) -> dict[str, set[str]]:
    """Edges point from the earlier story event to the later one."""
    edges: dict[str, set[str]] = {}
    for event in events:
        for earlier in event.after_event_ids:
            edges.setdefault(earlier, set()).add(event.id)
        for later in event.before_event_ids:
            edges.setdefault(event.id, set()).add(later)
    return edges


class StoryControlService:
    def __init__(
        self,
        repository: StoryControlRepository,
        structure: NovelStructureQueryService,
        characters: CharacterQueryService,
        memory: StoryMemoryService,
    ) -> None:
        self._repository = repository
        self._structure = structure
        self._characters = characters
        self._memory = memory
        # Composed only with the metered provider and budgets; None leaves proposals off.
        self.proposal_service: PlanProposalService | None = None
        self.foreshadow_service: ForeshadowExtractionService | None = None
        self.timeline_service: TimelineExtractionService | None = None

    # ------------------------------------------------------------------ helpers

    def _layout(self, project_id: str) -> Layout:
        volumes = self._structure.list_volumes(ListVolumesQuery(project_id))
        return Layout(
            project_id,
            tuple(volume.volume_id for volume in volumes),
            tuple(
                chapter
                for volume in volumes
                for chapter in self._structure.list_chapters(ListChaptersQuery(volume.volume_id))
            ),
        )

    def _chapter_project(self, chapter_id: str) -> str:
        return self._structure.get_chapter(GetChapterQuery(chapter_id)).project_id

    def _items(self, project_id: str) -> tuple[ControlItem, ...]:
        return self._repository.list(project_id)

    @staticmethod
    def _of[T](items: Iterable[ControlItem], kind: type[T]) -> list[T]:
        return [item for item in items if isinstance(item, kind)]

    def _require_chapter(self, layout: Layout, chapter_id: str | None) -> None:
        if chapter_id is not None and layout.chapter(chapter_id) is None:
            raise StoryControlInvalid

    def _require_characters(self, project_id: str, character_ids: Iterable[str]) -> None:
        for character_id in character_ids:
            try:
                character = self._characters.get_character(GetCharacterQuery(character_id))
            except (DomainError, ValueError):
                raise StoryControlInvalid from None
            if character.project_id != project_id:
                raise StoryControlInvalid

    def _require_evidence(
        self, layout: Layout, chapter_id: str, revision_id: str, quote: str
    ) -> None:
        chapter = layout.chapter(chapter_id)
        if chapter is None or chapter.current_revision_id != revision_id:
            raise StoryControlConflict
        content = self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))
        if content.current_revision_id != revision_id or quote not in content.content:
            raise StoryControlInvalid

    def _save[T: (Goal, Thread, Event, State)](
        self,
        project_id: str,
        entity_id: str | None,
        kind: type[T],
        expected_version: int,
        document: dict[str, object],
        validate: Callable[[Layout, list[T], T | None, T], None],
        limit: int,
        create_id: str | None = None,
    ) -> T:
        def previous_of(items: Iterable[ControlItem]) -> T | None:
            current = next(
                (item for item in self._of(items, kind) if item.id == entity_id),
                None,
            )
            if entity_id is not None and current is None:
                raise StoryControlNotFound
            return current

        previous = previous_of(self._items(project_id))
        if entity_id is None and expected_version != 0:
            raise StoryControlInvalid
        now = _now()
        item = kind.model_validate(
            {
                **document,
                "id": entity_id or create_id or str(uuid4()),
                "revision_id": str(uuid4()),
                "project_id": project_id,
                "version": expected_version + 1,
                "created_at": now if previous is None else previous.created_at,
                "updated_at": now,
            }
        )

        def checked(items: tuple[ControlItem, ...]) -> None:
            current = previous_of(items)
            same_kind = self._of(items, kind)
            if current is None and len(same_kind) >= limit:
                raise StoryControlInvalid
            validate(self._layout(project_id), same_kind, current, item)

        checked(self._items(project_id))
        saved = self._repository.save(item, expected_version, checked)
        assert isinstance(saved, kind)
        return saved

    # ------------------------------------------------------------------ goals

    def _validate_goal(
        self, layout: Layout, goals: list[Goal], previous: Goal | None, goal: Goal
    ) -> None:
        if goal.volume_id is not None and goal.volume_id not in layout.volume_ids:
            raise StoryControlInvalid
        known = {item.id for item in goals}
        if goal.id in goal.parent_goal_ids or any(
            parent not in known for parent in goal.parent_goal_ids
        ):
            raise StoryControlInvalid
        edges: dict[str, set[str]] = {}
        for item in [*(other for other in goals if other.id != goal.id), goal]:
            for parent in item.parent_goal_ids:
                edges.setdefault(parent, set()).add(item.id)
        if _has_cycle(edges):
            raise StoryControlCycle
        old_links = {} if previous is None else {link.chapter_id: link for link in previous.links}
        for link in goal.links:
            old = old_links.get(link.chapter_id)
            unchanged = old is not None and (old.chapter_revision_id, old.quote) == (
                link.chapter_revision_id,
                link.quote,
            )
            if not unchanged:
                self._require_chapter(layout, link.chapter_id)
                if link.quote is not None and link.chapter_revision_id is not None:
                    self._require_evidence(
                        layout, link.chapter_id, link.chapter_revision_id, link.quote
                    )

    def save_goal(self, project_id: str, goal_id: str | None, data: SaveGoal) -> Goal:
        return self._save(
            project_id,
            goal_id,
            Goal,
            data.expected_version,
            data.model_dump(exclude={"expected_version"}),
            self._validate_goal,
            MAX_GOALS,
        )

    def create_goal_with_id(self, project_id: str, goal_id: str, data: SaveGoal) -> Goal:
        """Create a goal under a caller-chosen id; an existing id is a version conflict.

        Plan proposal adoption uses a deterministic id per card, so a repeated or
        interrupted adoption can never create the same suggested goal twice.
        """
        if data.expected_version != 0:
            raise StoryControlInvalid
        return self._save(
            project_id,
            None,
            Goal,
            0,
            data.model_dump(exclude={"expected_version"}),
            self._validate_goal,
            MAX_GOALS,
            create_id=goal_id,
        )

    @staticmethod
    def _link_view(layout: Layout, link: GoalLink) -> LinkView:
        chapter = layout.chapter(link.chapter_id)
        problem: Literal["missing", "evidence_stale"] | None = (
            "missing"
            if chapter is None
            else "evidence_stale"
            if link.chapter_revision_id is not None
            and link.chapter_revision_id != chapter.current_revision_id
            else None
        )
        return LinkView(
            chapter_id=link.chapter_id,
            chapter_title=None if chapter is None else chapter.title,
            status=link.status,
            note=link.note,
            quote=link.quote,
            chapter_revision_id=link.chapter_revision_id,
            problem=problem,
        )

    def _goal_views(self, layout: Layout, goals: list[Goal]) -> list[GoalView]:
        views = []
        # Repository order is creation order; the sort is stable within one scope.
        ordered = sorted(
            goals,
            key=lambda item: (
                item.scope != "book",
                layout.volume_ids.index(item.volume_id)
                if item.volume_id in layout.volume_ids
                else len(layout.volume_ids),
            ),
        )
        for goal in ordered:
            views.append(
                GoalView(
                    goal=goal,
                    links=[self._link_view(layout, link) for link in goal.links],
                    child_goal_ids=[item.id for item in ordered if goal.id in item.parent_goal_ids],
                    reflected=sum(link.status == "reflected" for link in goal.links),
                    open_links=sum(link.status in ("planned", "deferred") for link in goal.links),
                )
            )
        return views

    def _character_options(self, project_id: str) -> list[CharacterOption]:
        options: list[CharacterOption] = []
        after = None
        while len(options) < MAX_CHARACTER_OPTIONS:
            page = self._characters.list_characters_for_project(
                ListCharactersForProjectQuery(project_id, MAX_CHARACTER_LIST_LIMIT, after)
            )
            options.extend(
                CharacterOption(character_id=item.character_id, name=item.name)
                for item in page.items
            )
            if not page.has_more:
                break
            after = page.next_position
        return options[:MAX_CHARACTER_OPTIONS]

    def character_options(self, project_id: str) -> list[CharacterOption]:
        """The project's characters (ids and names only), bounded; no model call."""
        return self._character_options(project_id)

    def arc_plan(self, project_id: str) -> ArcPlan:
        items = self._items(project_id)
        layout = self._layout(project_id)
        volumes = self._structure.list_volumes(ListVolumesQuery(project_id))
        return ArcPlan(
            project_id=project_id,
            goals=self._goal_views(layout, self._of(items, Goal)),
            volumes=[
                VolumeOption(volume_id=item.volume_id, title=item.title, position=index + 1)
                for index, item in enumerate(volumes)
            ],
            chapters=[
                ChapterOption(
                    chapter_id=item.chapter_id,
                    volume_id=item.volume_id,
                    title=item.title,
                    volume_position=layout.volume_position(item.volume_id),
                    position=item.position,
                    revision_id=item.current_revision_id,
                )
                for item in layout.chapters
            ],
            characters=self._character_options(project_id),
        )

    # ------------------------------------------------------------------ threads

    def _validate_thread(
        self, layout: Layout, _threads: list[Thread], previous: Thread | None, thread: Thread
    ) -> None:
        self._require_characters(layout.project_id, thread.character_ids)
        self._require_chapter(layout, thread.planned_setup_chapter_id)
        self._require_chapter(layout, thread.planned_payoff_chapter_id)
        if (
            thread.planned_payoff_volume_id is not None
            and thread.planned_payoff_volume_id not in layout.volume_ids
        ):
            raise StoryControlInvalid
        old = set() if previous is None else set(previous.anchors)
        for anchor in thread.anchors:
            if anchor not in old:
                self._require_evidence(
                    layout, anchor.chapter_id, anchor.chapter_revision_id, anchor.quote
                )

    def save_thread(self, project_id: str, thread_id: str | None, data: SaveThread) -> Thread:
        return self._save(
            project_id,
            thread_id,
            Thread,
            data.expected_version,
            data.model_dump(exclude={"expected_version"}),
            self._validate_thread,
            MAX_THREADS,
        )

    def create_thread_with_id(self, project_id: str, thread_id: str, data: SaveThread) -> Thread:
        """Create a thread under a caller-chosen id; an existing id is a version conflict.

        Foreshadow extraction adoption uses a deterministic id per card, so a repeated or
        interrupted adoption can never create the same suggested thread twice.
        """
        if data.expected_version != 0:
            raise StoryControlInvalid
        return self._save(
            project_id,
            None,
            Thread,
            0,
            data.model_dump(exclude={"expected_version"}),
            self._validate_thread,
            MAX_THREADS,
            create_id=thread_id,
        )

    def list_threads(self, project_id: str) -> list[Thread]:
        return self._of(self._items(project_id), Thread)

    def chapter_revisions(self, project_id: str) -> dict[str, str]:
        """Current saved revision of every chapter in the project, in book order."""
        return {
            item.chapter_id: item.current_revision_id for item in self._layout(project_id).chapters
        }

    def chapter_texts(
        self, project_id: str, chapter_ids: Iterable[str]
    ) -> list[tuple[ChapterOption, str]]:
        """Saved text of the chosen chapters of this project, in book order; no model call."""
        layout = self._layout(project_id)
        wanted = set(chapter_ids)
        if any(layout.chapter(chapter_id) is None for chapter_id in wanted):
            raise StoryControlInvalid
        result = []
        for item in layout.chapters:
            if item.chapter_id not in wanted:
                continue
            content = self._structure.get_chapter_content(GetChapterContentQuery(item.chapter_id))
            result.append(
                (
                    ChapterOption(
                        chapter_id=item.chapter_id,
                        volume_id=item.volume_id,
                        title=item.title,
                        volume_position=layout.volume_position(item.volume_id),
                        position=item.position,
                        revision_id=content.current_revision_id,
                    ),
                    content.content,
                )
            )
        return result

    def _payoff_reached(self, layout: Layout, thread: Thread) -> str | None:
        target: ChapterSnapshot | None = None
        if thread.planned_payoff_chapter_id is not None:
            target = layout.chapter(thread.planned_payoff_chapter_id)
            reason = "预计兑现章已有正文，请兑现、延期、改计划或放弃"
        elif thread.planned_payoff_volume_id is not None:
            in_volume = [
                item
                for item in layout.chapters
                if item.volume_id == thread.planned_payoff_volume_id
            ]
            target = in_volume[-1] if in_volume else None
            reason = "预计兑现卷的最后一章已有正文，请兑现、延期、改计划或放弃"
        if target is None:
            return None
        content = self._structure.get_chapter_content(GetChapterContentQuery(target.chapter_id))
        return reason if _has_text(content.content) else None

    def _thread_view(self, layout: Layout, thread: Thread) -> ThreadView:
        anchors = []
        for anchor in thread.anchors:
            chapter = layout.chapter(anchor.chapter_id)
            anchors.append(
                AnchorView(
                    anchor=anchor,
                    chapter_title=None if chapter is None else chapter.title,
                    stale=chapter is None
                    or chapter.current_revision_id != anchor.chapter_revision_id,
                )
            )
        stale = any(item.stale for item in anchors)
        due_reason = (
            self._payoff_reached(layout, thread) if thread.status in OPEN_THREAD_STATUSES else None
        )
        if due_reason is None and stale and thread.status != "abandoned":
            due_reason = "伏笔证据所在正文已修改，证据待复核"
        return ThreadView(
            thread=thread,
            anchors=anchors,
            evidence_stale=stale,
            due=due_reason is not None,
            due_reason=due_reason,
        )

    # ------------------------------------------------------------------ events and states

    def _validate_event(
        self, layout: Layout, events: list[Event], _previous: Event | None, event: Event
    ) -> None:
        self._require_chapter(layout, event.chapter_id)
        self._require_characters(layout.project_id, event.character_ids)
        known = {item.id for item in events}
        related = (*event.after_event_ids, *event.before_event_ids)
        if event.id in related or any(item not in known for item in related):
            raise StoryControlInvalid
        if _has_cycle(_event_edges([*(item for item in events if item.id != event.id), event])):
            raise StoryControlCycle

    def save_event(self, project_id: str, event_id: str | None, data: SaveEvent) -> Event:
        return self._save(
            project_id,
            event_id,
            Event,
            data.expected_version,
            data.model_dump(exclude={"expected_version"}),
            self._validate_event,
            MAX_EVENTS,
        )

    def create_event_with_id(self, project_id: str, event_id: str, data: SaveEvent) -> Event:
        """Create an event under a caller-chosen id; an existing id is a version conflict.

        Timeline extraction adoption uses a deterministic id per card, so a repeated or
        interrupted adoption can never create the same suggested event twice.
        """
        if data.expected_version != 0:
            raise StoryControlInvalid
        return self._save(
            project_id,
            None,
            Event,
            0,
            data.model_dump(exclude={"expected_version"}),
            self._validate_event,
            MAX_EVENTS,
            create_id=event_id,
        )

    def list_events(self, project_id: str) -> list[Event]:
        return self._of(self._items(project_id), Event)

    def list_states(self, project_id: str) -> list[State]:
        return self._of(self._items(project_id), State)

    def _validate_state(
        self, layout: Layout, _states: list[State], _previous: State | None, state: State
    ) -> None:
        self._require_characters(layout.project_id, (state.character_id,))
        events = self._of(self._items(layout.project_id), Event)
        known = {item.id for item in events}
        if state.start_event_id not in known or (
            state.end_event_id is not None and state.end_event_id not in known
        ):
            raise StoryControlInvalid
        if state.end_event_id is not None and _reachable(
            _event_edges(events), state.end_event_id, state.start_event_id
        ):
            raise StoryControlInvalid
        facts, _ = self._memory.project_facts(layout.project_id)
        confirmed = {item.id for item in facts if item.status == "confirmed" and not item.stale}
        if any(fact_id not in confirmed for fact_id in state.fact_ids):
            raise StoryControlInvalid

    def save_state(self, project_id: str, state_id: str | None, data: SaveState) -> State:
        return self._save(
            project_id,
            state_id,
            State,
            data.expected_version,
            data.model_dump(exclude={"expected_version"}),
            self._validate_state,
            MAX_STATES,
        )

    def create_state_with_id(self, project_id: str, state_id: str, data: SaveState) -> State:
        """Create a state interval under a caller-chosen id (see ``create_event_with_id``)."""
        if data.expected_version != 0:
            raise StoryControlInvalid
        return self._save(
            project_id,
            None,
            State,
            0,
            data.model_dump(exclude={"expected_version"}),
            self._validate_state,
            MAX_STATES,
            create_id=state_id,
        )

    @staticmethod
    def _event_views(layout: Layout, events: list[Event]) -> list[EventView]:
        active = [item for item in events if not item.archived]
        ids = {item.id for item in active}
        edges = {
            node: {target for target in targets if target in ids}
            for node, targets in _event_edges(active).items()
            if node in ids
        }

        created = {item.id: index for index, item in enumerate(events)}

        def narrative(event: Event) -> tuple[int, int, int]:
            chapter = layout.chapter(event.chapter_id)
            index = len(layout.chapters) if chapter is None else layout.index(chapter.chapter_id)
            return (0 if chapter is not None else 1, index, created[event.id])

        incoming = {item.id: 0 for item in active}
        for targets in edges.values():
            for target in targets:
                incoming[target] += 1
        by_id = {item.id: item for item in active}
        ready = sorted((by_id[i] for i, count in incoming.items() if count == 0), key=narrative)
        ordered: list[Event] = []
        while ready:
            event = ready.pop(0)
            ordered.append(event)
            for target in edges.get(event.id, ()):
                incoming[target] -= 1
                if incoming[target] == 0:
                    ready.append(by_id[target])
            ready.sort(key=narrative)
        views = []
        for index, event in enumerate(ordered):
            chapter = layout.chapter(event.chapter_id)
            views.append(
                EventView(
                    event=event,
                    story_order=index + 1,
                    narrative_position=None
                    if chapter is None
                    else [layout.volume_position(chapter.volume_id), chapter.position],
                    chapter_title=None if chapter is None else chapter.title,
                )
            )
        return views

    @staticmethod
    def _warnings(events: list[Event], states: list[State]) -> list[TimelineWarning]:
        edges = _event_edges(events)

        def before(first: str, second: str) -> bool:
            return first == second or _reachable(edges, first, second)

        def disjoint(a: State, b: State) -> bool:
            return (a.end_event_id is not None and before(a.end_event_id, b.start_event_id)) or (
                b.end_event_id is not None and before(b.end_event_id, a.start_event_id)
            )

        warnings = []
        active = [item for item in states if not item.archived]
        for index, first in enumerate(active):
            for second in active[index + 1 :]:
                if (first.character_id, first.attribute, first.label) != (
                    second.character_id,
                    second.attribute,
                    second.label,
                ) or first.value == second.value:
                    continue
                if disjoint(first, second):
                    continue
                known = before(first.start_event_id, second.start_event_id) or before(
                    second.start_event_id, first.start_event_id
                )
                warnings.append(
                    TimelineWarning(
                        kind="state_overlap" if known else "state_order_unknown",
                        state_ids=[first.id, second.id],
                        message=(
                            f"「{first.label}」的两个不同状态区间重叠，请核对"
                            if known
                            else f"「{first.label}」的两个状态区间先后未知，可能重叠，请补充事件关系"
                        ),
                    )
                )
        return warnings

    def timeline(
        self,
        project_id: str,
        character_id: str | None = None,
        volume_id: str | None = None,
        status: ThreadStatus | None = None,
    ) -> Timeline:
        items = self._items(project_id)
        layout = self._layout(project_id)
        if volume_id is not None and volume_id not in layout.volume_ids:
            raise StoryControlNotFound
        volume_chapters = (
            None
            if volume_id is None
            else {item.chapter_id for item in layout.chapters if item.volume_id == volume_id}
        )
        events = self._of(items, Event)
        states = self._of(items, State)
        facts, _ = self._memory.project_facts(project_id)
        confirmed = {item.id for item in facts if item.status == "confirmed" and not item.stale}

        def in_volume(chapters: Iterable[str | None]) -> bool:
            return volume_chapters is None or any(item in volume_chapters for item in chapters)

        threads = [
            self._thread_view(layout, thread)
            for thread in self._of(items, Thread)
            if (character_id is None or character_id in thread.character_ids)
            and (status is None or thread.status == status)
            and (
                in_volume(
                    (
                        thread.planned_setup_chapter_id,
                        thread.planned_payoff_chapter_id,
                        *(anchor.chapter_id for anchor in thread.anchors),
                    )
                )
                or (volume_id is not None and thread.planned_payoff_volume_id == volume_id)
            )
        ]
        event_views = [
            view
            for view in self._event_views(layout, events)
            if (character_id is None or character_id in view.event.character_ids)
            and in_volume((view.event.chapter_id,))
        ]
        state_views = [
            StateView(
                state=state,
                invalid_fact_ids=[item for item in state.fact_ids if item not in confirmed],
            )
            for state in states
            if (character_id is None or state.character_id == character_id) and not state.archived
        ]
        warnings = [
            warning
            for warning in self._warnings(events, states)
            if character_id is None
            or any(
                state.id in warning.state_ids and state.character_id == character_id
                for state in states
            )
        ]
        return Timeline(
            project_id=project_id,
            threads=threads,
            events=event_views,
            states=state_views,
            warnings=warnings,
        )

    # ------------------------------------------------------------------ chapter guide

    def chapter_guide(self, chapter_id: str) -> ChapterGuide:
        chapter = self._structure.get_chapter(GetChapterQuery(chapter_id))
        project_id = chapter.project_id
        items = self._items(project_id)
        layout = self._layout(project_id)
        goals = [
            goal
            for goal in self._of(items, Goal)
            if goal.status == "active" and any(link.chapter_id == chapter_id for link in goal.links)
        ]
        threads = [self._thread_view(layout, item) for item in self._of(items, Thread)]
        return ChapterGuide(
            chapter_id=chapter_id,
            project_id=project_id,
            goals=self._goal_views(layout, goals),
            setup_threads=[
                view
                for view in threads
                if view.thread.planned_setup_chapter_id == chapter_id
                and view.thread.status == "planned"
            ],
            payoff_threads=[
                view
                for view in threads
                if view.thread.status in OPEN_THREAD_STATUSES
                and (
                    view.thread.planned_payoff_chapter_id == chapter_id
                    or view.thread.planned_payoff_volume_id == chapter.volume_id
                )
            ],
            due_threads=[view for view in threads if view.due],
        )

    def guide_sources(self, chapter_id: str) -> tuple[ContextSource, ...]:
        """Author plans for this chapter as labelled guidance, never as story facts."""
        guide = self.chapter_guide(chapter_id)
        lines: list[str] = []
        references: list[tuple[str, str]] = []
        for view in guide.goals:
            goal = view.goal
            link = next(item for item in goal.links if item.chapter_id == chapter_id)
            references.append((goal.id, goal.revision_id))
            scope = "全书目标" if goal.scope == "book" else "分卷目标"
            parts = [f"{scope}: {goal.title}"]
            for label, value in (
                ("冲突", goal.conflict),
                ("阻碍", goal.obstacle),
                ("转折", goal.turn),
                ("预期变化", goal.outcome),
                ("本章说明", link.note),
            ):
                if value.strip():
                    parts.append(f"{label}: {value.strip()}")
            lines.append("\n".join(parts))
        for label, views in (
            ("本章计划埋设的伏笔", guide.setup_threads),
            ("计划在本章或本卷兑现的伏笔", guide.payoff_threads),
        ):
            for thread_view in views:
                thread = thread_view.thread
                if (thread.id, thread.revision_id) in references:
                    continue
                references.append((thread.id, thread.revision_id))
                lines.append(f"{label}: {thread.title}\n{thread.content.strip()}".rstrip())
        if not lines:
            return ()
        text = "\n\n".join(lines)
        bounded = text[:GUIDE_CHARACTER_LIMIT]
        return (
            ContextSource(
                "story_guide",
                tuple(references),
                bounded,
                "作者计划(不是已发生的正文事实):本章关联的全书/卷目标及计划埋设或兑现的伏笔",
                None,
                len(bounded) != len(text),
            ),
        )

    # ------------------------------------------------------------------ recall

    def _policy(self, chapter_id: str, project_id: str) -> RecallPolicy | None:
        return next(
            (
                item
                for item in self._of(self._items(project_id), RecallPolicy)
                if item.chapter_id == chapter_id
            ),
            None,
        )

    def recall_policy(self, chapter_id: str) -> RecallPolicy | None:
        return self._policy(chapter_id, self._chapter_project(chapter_id))

    def selection_policy(self, chapter_id: str) -> RecallSelectionPolicy | None:
        policy = self.recall_policy(chapter_id)
        return (
            None
            if policy is None
            else RecallSelectionPolicy(
                policy.version, tuple(policy.pinned_fact_ids), tuple(policy.excluded_fact_ids)
            )
        )

    def save_recall_policy(self, chapter_id: str, data: SaveRecallPolicy) -> RecallPolicy:
        project_id = self._chapter_project(chapter_id)
        previous = self._policy(chapter_id, project_id)
        now = _now()
        policy = RecallPolicy(
            id=chapter_id if previous is None else previous.id,
            revision_id=str(uuid4()),
            project_id=project_id,
            chapter_id=chapter_id,
            version=data.expected_version + 1,
            created_at=now if previous is None else previous.created_at,
            updated_at=now,
            pinned_fact_ids=data.pinned_fact_ids,
            excluded_fact_ids=data.excluded_fact_ids,
        )

        def validate(_items: tuple[ControlItem, ...]) -> None:
            _, outcome = self._memory.recall_for_chapter(
                chapter_id, RecallSelectionPolicy(policy.version, tuple(data.pinned_fact_ids), ())
            )
            facts = {item.id for item in outcome.facts}
            invalid_pins = [
                fact_id
                for fact_id, _title, reason in outcome.omitted
                if reason in ("pin_missing", "pin_not_confirmed", "pin_stale", "pin_not_earlier")
            ]
            if invalid_pins or any(item not in facts for item in data.excluded_fact_ids):
                raise StoryControlInvalid

        validate(())
        saved = self._repository.save(policy, data.expected_version, validate)
        assert isinstance(saved, RecallPolicy)
        return saved

    def recall_preview(
        self, chapter_id: str, draft: RecallPolicyDocument | None = None
    ) -> RecallPreview:
        saved = self.recall_policy(chapter_id)
        source = draft if draft is not None else saved
        policy = (
            None
            if source is None
            else RecallSelectionPolicy(
                0 if saved is None else saved.version,
                tuple(source.pinned_fact_ids),
                tuple(source.excluded_fact_ids),
            )
        )
        _, outcome = self._memory.recall_for_chapter(chapter_id, policy)
        titles = {item.id: item.title for item in outcome.facts}
        return RecallPreview(
            chapter_id=chapter_id,
            policy_version=0 if saved is None else saved.version,
            selected=[
                RecallChoice(
                    id=item.id,
                    revision_id=item.revision_id,
                    chapter_id=item.chapter_id,
                    title=titles.get(item.id, item.title),
                    reason="pinned" if outcome.reasons[item.id] == "pinned" else "related",
                    characters=outcome.costs[item.id],
                )
                for item in outcome.selected
            ],
            omitted=[
                RecallOmission.model_validate({"id": fact_id, "title": title, "reason": reason})
                for fact_id, title, reason in outcome.omitted[:100]
            ],
            omitted_total=outcome.omitted_total,
            excluded_total=outcome.excluded_total,
            used_characters=outcome.used,
            character_limit=RECALL_CHARACTER_LIMIT,
            item_limit=RECALL_ITEM_LIMIT,
            blocked=outcome.blocked,
        )

    def search_facts(
        self,
        project_id: str,
        *,
        query: str = "",
        chapter_id: str | None = None,
        status: str | None = None,
        for_chapter: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> FactSearchPage:
        facts, chapters = self._memory.project_facts(project_id)
        order = {item.chapter_id: index for index, item in enumerate(chapters)}
        titles = {item.chapter_id: item.title for item in chapters}
        if for_chapter is not None and for_chapter not in order:
            raise StoryControlNotFound
        needle = query.strip().casefold()

        def matches(item: Fact) -> bool:
            return (
                (not needle or needle in f"{item.title}\n{item.text}\n{item.quote}".casefold())
                and (chapter_id is None or item.chapter_id == chapter_id)
                and (status is None or item.status == status)
            )

        hits = sorted(
            (item for item in facts if matches(item)),
            key=lambda item: (order.get(item.chapter_id, len(order)), item.title, item.id),
        )
        return FactSearchPage(
            items=[
                FactHit(
                    id=item.id,
                    revision_id=item.revision_id,
                    chapter_id=item.chapter_id,
                    chapter_title=titles.get(item.chapter_id),
                    title=item.title,
                    text=item.text,
                    quote=item.quote,
                    status=item.status,
                    stale=item.stale,
                    recallable_here=None
                    if for_chapter is None
                    else item.status == "confirmed"
                    and not item.stale
                    and order.get(item.chapter_id, len(order)) < order[for_chapter],
                )
                for item in hits[offset : offset + limit]
            ],
            total=len(hits),
            offset=offset,
            limit=limit,
        )

"""Plan, confirm and build the semantic index; rank recall from stored vectors only.

No method here calls a model except ``build``, and ``build`` only after the author
confirmed the exact plan (``plan_version`` binds the items, the embedding profile and
the shown estimate). Every request goes through the injected metered embedder under the
``semantic_index`` usage operation and the author's budget.
"""

import hashlib
import json
import math
from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.novel_structure.application.models import ChapterContentSnapshot
from aiwebnovel.novel_structure.application.queries import GetChapterContentQuery
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.semantic_index.models import (
    BATCH_CHARACTERS,
    BATCH_INPUTS,
    CHUNK_CHARACTERS,
    MAX_CHUNKS_PER_CHAPTER,
    MAX_ITEMS_PER_BUILD,
    QUERY_CHUNKS,
    BuildResult,
    EmbeddingModel,
    Entry,
    IndexStatus,
    PlanItem,
    PlanView,
    ProfileProblem,
    ProfileView,
    SemanticIndexConfirmationRequired,
    SemanticIndexConflict,
    SemanticIndexInvalid,
    SemanticIndexNothingToDo,
    SemanticRanking,
    Settings,
    SettingsView,
)
from aiwebnovel.story_memory.models import Fact
from aiwebnovel.story_memory.service import StoryMemoryService
from aiwebnovel.usage.attribution import usage_attribution
from aiwebnovel.usage.budget import BudgetRefused, SendEstimate


class SemanticIndexStore(Protocol):
    def settings(self, project_id: str) -> Settings: ...

    def save_settings(
        self, project_id: str, expected_version: int, enabled: bool, profile_id: str | None
    ) -> Settings: ...

    def entries(self, project_id: str) -> tuple[Entry, ...]: ...

    def replace(self, project_id: str, entries: tuple[Entry, ...]) -> int: ...

    def remove(self, project_id: str, keys: tuple[tuple[str, str], ...]) -> int: ...


# (profile id, texts, expected (kind, base_url, model)) -> one vector per text, in order.
Embedder = Callable[[str, tuple[str, ...], tuple[str, str, str]], tuple[tuple[float, ...], ...]]
Estimator = Callable[..., SendEstimate]
ProfileReader = Callable[[str], EmbeddingModel | None]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_hash(profile: EmbeddingModel) -> str:
    return _hash(json.dumps([profile.id, profile.kind, profile.base_url, profile.model]))


def fact_text(fact: Fact) -> str:
    return f"{fact.title}\n{fact.text}"


def chapter_chunks(content: str) -> tuple[str, ...]:
    """Fixed-size chunks; a very long chapter keeps its last chunks (the query window)."""
    chunks = tuple(
        content[start : start + CHUNK_CHARACTERS]
        for start in range(0, len(content), CHUNK_CHARACTERS)
        if content[start : start + CHUNK_CHARACTERS].strip()
    )
    return chunks[-MAX_CHUNKS_PER_CHAPTER:]


def _normalized(vector: tuple[float, ...]) -> tuple[float, ...] | None:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm or not math.isfinite(norm):
        return None
    return tuple(value / norm for value in vector)


def batches(items: tuple[PlanItem, ...]) -> tuple[tuple[PlanItem, ...], ...]:
    result: list[tuple[PlanItem, ...]] = []
    current: list[PlanItem] = []
    size = 0
    for item in items:
        if current and (len(current) >= BATCH_INPUTS or size + len(item.text) > BATCH_CHARACTERS):
            result.append(tuple(current))
            current, size = [], 0
        current.append(item)
        size += len(item.text)
    if current:
        result.append(tuple(current))
    return tuple(result)


class _Snapshot:
    """Everything one status/plan/build/rank decision is computed from."""

    def __init__(
        self,
        settings: Settings,
        profile: EmbeddingModel | None,
        problem: ProfileProblem | None,
        expected: tuple[PlanItem, ...],
        entries: tuple[Entry, ...],
        facts: int,
        chapters: dict[str, int],
    ) -> None:
        self.settings = settings
        self.profile = profile
        self.problem = problem
        self.expected = expected
        self.entries = entries
        self.facts = facts
        self.chapter_chunk_counts = chapters
        config = None if profile is None else config_hash(profile)
        by_key = {(entry.kind, entry.source_id): entry for entry in entries}
        self.valid: dict[tuple[str, str], Entry] = {}
        self.missing: list[PlanItem] = []
        for item in expected:
            entry = by_key.get((item.kind, item.source_id))
            if (
                entry is not None
                and profile is not None
                and entry.profile_id == profile.id
                and entry.config_hash == config
                and entry.source_revision == item.source_revision
                and entry.text_hash == item.text_hash
            ):
                self.valid[(item.kind, item.source_id)] = entry
            else:
                self.missing.append(item)
        keys = {(item.kind, item.source_id) for item in expected}
        self.obsolete = tuple(key for key in by_key if key not in keys)
        self.stale = sum(1 for item in self.missing if (item.kind, item.source_id) in by_key) + len(
            self.obsolete
        )

    def chapter_indexed(self, chapter_id: str) -> bool:
        expected = self.chapter_chunk_counts.get(chapter_id, 0)
        return expected > 0 and all(
            ("chapter_chunk", f"{chapter_id}#{index}") in self.valid for index in range(expected)
        )


class SemanticIndexService:
    def __init__(
        self,
        store: SemanticIndexStore,
        memory: StoryMemoryService,
        structure: NovelStructureQueryService,
        profiles: ProfileReader,
        embedder: Embedder,
        estimator: Estimator,
    ) -> None:
        self._store = store
        self._memory = memory
        self._structure = structure
        self._profiles = profiles
        self._embedder = embedder
        self._estimator = estimator

    # -- settings ---------------------------------------------------------------------

    def _profile(
        self, profile_id: str | None
    ) -> tuple[EmbeddingModel | None, ProfileProblem | None]:
        if profile_id is None:
            return None, "not_configured"
        profile = self._profiles(profile_id)
        if profile is None:
            return None, "not_found"
        if profile.purpose != "embedding":
            return None, "not_embedding"
        return profile, None

    def save_settings(
        self, project_id: str, expected_version: int, enabled: bool, profile_id: str | None
    ) -> SettingsView:
        self._memory.project_facts(project_id)  # visibility check, no model request
        if profile_id is not None and self._profile(profile_id)[1] is not None:
            raise SemanticIndexInvalid
        if enabled and profile_id is None:
            raise SemanticIndexInvalid
        saved = self._store.save_settings(project_id, expected_version, enabled, profile_id)
        return SettingsView(
            version=saved.version,
            enabled=saved.enabled,
            profile_id=saved.profile_id,
            updated_at=saved.updated_at,
        )

    # -- snapshot / plan --------------------------------------------------------------

    def _chapter(self, chapter_id: str) -> ChapterContentSnapshot:
        return self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))

    def _snapshot(self, project_id: str) -> _Snapshot:
        facts, chapters = self._memory.project_facts(project_id)
        settings = self._store.settings(project_id)
        profile, problem = self._profile(settings.profile_id)
        expected: list[PlanItem] = []
        eligible = [item for item in facts if item.status == "confirmed" and not item.stale]
        for fact in eligible:
            text = fact_text(fact)
            expected.append(
                PlanItem("fact", fact.id, fact.chapter_id, fact.revision_id, text, _hash(text))
            )
        counts: dict[str, int] = {}
        for summary in chapters:
            chapter = self._chapter(summary.chapter_id)
            chunks = chapter_chunks(chapter.content)
            counts[chapter.chapter_id] = len(chunks)
            for index, text in enumerate(chunks):
                expected.append(
                    PlanItem(
                        "chapter_chunk",
                        f"{chapter.chapter_id}#{index}",
                        chapter.chapter_id,
                        chapter.current_revision_id,
                        text,
                        _hash(text),
                    )
                )
        return _Snapshot(
            settings,
            profile,
            problem,
            tuple(expected),
            self._store.entries(project_id),
            len(eligible),
            counts,
        )

    def _plan(
        self, project_id: str, snapshot: _Snapshot
    ) -> tuple[tuple[PlanItem, ...], PlanView, SendEstimate] | None:
        profile = snapshot.profile
        if profile is None or not (snapshot.missing or snapshot.obsolete):
            return None
        items = tuple(snapshot.missing[:MAX_ITEMS_PER_BUILD])
        groups = batches(items)
        estimate = (
            self._estimator(
                project_id=project_id,
                task_id="semantic-index-plan",
                profile_id=profile.id,
                batches=tuple(tuple(item.text for item in group) for group in groups),
            )
            if groups
            else None
        )
        version = _hash(
            json.dumps(
                {
                    "profile": [profile.id, profile.kind, profile.base_url, profile.model],
                    "items": [
                        [item.kind, item.source_id, item.source_revision, item.text_hash]
                        for item in items
                    ],
                    "obsolete": sorted(snapshot.obsolete),
                    "estimate": None if estimate is None else estimate.model_dump(mode="json"),
                },
                sort_keys=True,
                ensure_ascii=True,
            )
        )
        view = PlanView(
            plan_version=version,
            fact_items=sum(item.kind == "fact" for item in items),
            chunk_items=sum(item.kind == "chapter_chunk" for item in items),
            requests=len(groups),
            input_characters=sum(len(item.text) for item in items),
            deferred_items=max(0, len(snapshot.missing) - len(items)),
            obsolete_entries=len(snapshot.obsolete),
        )
        # An empty plan with only obsolete rows to prune needs no estimate or request.
        return items, view, estimate if estimate is not None else _no_estimate(profile.id)

    def status(self, project_id: str) -> IndexStatus:
        """Counts, the incremental plan and its estimate. Never calls a model."""
        snapshot = self._snapshot(project_id)
        plan = self._plan(project_id, snapshot)
        return self._status(project_id, snapshot, plan)

    def _status(
        self,
        project_id: str,
        snapshot: _Snapshot,
        plan: tuple[tuple[PlanItem, ...], PlanView, SendEstimate] | None,
    ) -> IndexStatus:
        profile = snapshot.profile
        settings = snapshot.settings
        return IndexStatus(
            project_id=project_id,
            settings=SettingsView(
                version=settings.version,
                enabled=settings.enabled,
                profile_id=settings.profile_id,
                updated_at=settings.updated_at,
            ),
            profile=None
            if profile is None
            else ProfileView(
                id=profile.id,
                name=profile.name,
                kind="cloud" if profile.kind == "cloud" else "local",
                model=profile.model,
            ),
            profile_problem=snapshot.problem,
            facts_total=snapshot.facts,
            facts_indexed=sum(1 for kind, _ in snapshot.valid if kind == "fact"),
            chapters_total=sum(1 for count in snapshot.chapter_chunk_counts.values() if count),
            chapters_indexed=sum(
                1
                for chapter_id in snapshot.chapter_chunk_counts
                if snapshot.chapter_indexed(chapter_id)
            ),
            stale_entries=snapshot.stale,
            up_to_date=profile is not None and not snapshot.missing and not snapshot.obsolete,
            plan=None if plan is None else plan[1],
            estimate=None if plan is None or plan[1].requests == 0 else plan[2],
        )

    # -- build ------------------------------------------------------------------------

    def build(
        self, project_id: str, plan_version: str, *, confirmed: bool, cloud_consent: bool
    ) -> BuildResult:
        """Embed exactly the confirmed plan. Partial progress of a failed build is kept."""
        if not confirmed:
            raise SemanticIndexConfirmationRequired
        snapshot = self._snapshot(project_id)
        plan = self._plan(project_id, snapshot)
        if plan is None:
            raise SemanticIndexNothingToDo
        items, view, estimate = plan
        profile = snapshot.profile
        assert profile is not None
        if view.plan_version != plan_version:
            raise SemanticIndexConflict
        if profile.kind == "cloud" and not cloud_consent:
            raise SemanticIndexConfirmationRequired
        if view.requests and estimate.decision == "refused":
            # The whole build would exceed a strict budget: nothing is sent.
            raise BudgetRefused
        build_id = str(uuid4())
        config = (profile.kind, profile.base_url, profile.model)
        digest = config_hash(profile)
        dimensions: int | None = None
        sent = indexed = 0
        with usage_attribution("semantic_index", build_id, project_id=project_id):
            for group in batches(items):
                sent += 1
                vectors = self._embedder(profile.id, tuple(item.text for item in group), config)
                if len(vectors) != len(group):
                    raise SemanticIndexInvalid
                entries: list[Entry] = []
                for item, raw in zip(group, vectors, strict=True):
                    vector = _normalized(raw)
                    if vector is None or (dimensions is not None and len(vector) != dimensions):
                        raise SemanticIndexInvalid
                    dimensions = len(vector)
                    entries.append(
                        Entry(
                            item.kind,
                            item.source_id,
                            item.chapter_id,
                            item.source_revision,
                            profile.id,
                            digest,
                            item.text_hash,
                            vector,
                        )
                    )
                indexed += self._store.replace(project_id, tuple(entries))
        removed = self._store.remove(project_id, snapshot.obsolete) if snapshot.obsolete else 0
        return BuildResult(
            build_id=build_id,
            requests_sent=sent,
            items_indexed=indexed,
            entries_removed=removed,
            status=self.status(project_id),
        )

    # -- recall ranking ---------------------------------------------------------------

    def rank(
        self, chapter: ChapterContentSnapshot, candidates: tuple[Fact, ...]
    ) -> SemanticRanking:
        """Similarity of each candidate to the current chapter, from stored vectors only."""
        settings = self._store.settings(chapter.project_id)
        if not settings.enabled:
            return SemanticRanking(False, False, None, {})
        profile, problem = self._profile(settings.profile_id)
        if profile is None or problem is not None:
            return SemanticRanking(True, False, "所选嵌入模型配置不可用", {})
        digest = config_hash(profile)
        entries = {
            (entry.kind, entry.source_id): entry
            for entry in self._store.entries(chapter.project_id)
            if entry.profile_id == profile.id and entry.config_hash == digest
        }
        chunks = chapter_chunks(chapter.content)
        query_vectors: list[tuple[float, ...]] = []
        for index, text in enumerate(chunks):
            entry = entries.get(("chapter_chunk", f"{chapter.chapter_id}#{index}"))
            if (
                entry is None
                or entry.source_revision != chapter.current_revision_id
                or entry.text_hash != _hash(text)
            ):
                return SemanticRanking(
                    True, False, "本章正文尚未建立语义索引或已修改，请增量更新索引", {}
                )
            if index >= len(chunks) - QUERY_CHUNKS:
                query_vectors.append(entry.vector)
        if not query_vectors:
            return SemanticRanking(True, False, "本章正文为空，无法语义召回", {})
        dimensions = len(query_vectors[0])
        missing = 0
        fact_vectors: dict[str, tuple[float, ...]] = {}
        for fact in candidates:
            entry = entries.get(("fact", fact.id))
            if (
                entry is None
                or entry.source_revision != fact.revision_id
                or entry.text_hash != _hash(fact_text(fact))
                or len(entry.vector) != dimensions
            ):
                missing += 1
            else:
                fact_vectors[fact.id] = entry.vector
        if missing:
            return SemanticRanking(
                True, False, f"有 {missing} 项可召回事实尚未建立语义索引或索引已过期", {}
            )
        if any(len(vector) != dimensions for vector in query_vectors):
            return SemanticRanking(True, False, "本章索引向量维度不一致，请重新建立索引", {})
        mean = tuple(
            sum(vector[axis] for vector in query_vectors) / len(query_vectors)
            for axis in range(dimensions)
        )
        query = _normalized(mean)
        if query is None:
            return SemanticRanking(True, False, "本章索引向量无效，请重新建立索引", {})
        return SemanticRanking(
            True,
            True,
            None,
            {
                fact_id: max(-1.0, min(1.0, sum(a * b for a, b in zip(query, vector, strict=True))))
                for fact_id, vector in fact_vectors.items()
            },
        )

    def safe_rank(
        self, chapter: ChapterContentSnapshot, candidates: tuple[Fact, ...]
    ) -> SemanticRanking:
        """Ranking problems never break recall: report a fallback instead."""
        try:
            return self.rank(chapter, candidates)
        except DomainError:
            return SemanticRanking(True, False, "语义索引暂不可读取", {})


def _no_estimate(profile_id: str) -> SendEstimate:
    return SendEstimate(
        profile_id=profile_id,
        input_characters=0,
        input_tokens_upper=0,
        output_tokens_upper=0,
        price=None,
        estimated_cost_upper=None,
        currency=None,
        budget_mode="off",
        budget_currency=None,
        task_limit=None,
        monthly_limit=None,
        task_spent_upper=None,
        month_spent_upper=None,
        unpriced_attempts=0,
        decision="allowed",
        reasons=[],
    )

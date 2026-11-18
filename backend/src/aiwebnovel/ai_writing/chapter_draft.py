"""F05 extension: a bounded, author-confirmed whole-chapter candidate draft (``chapter_draft``).

Preparation freezes the chapter's saved revision, the labelled writing context and the quota
without any model request. Each explicit send generates at most the number of segments the
author confirmed, one metered request at a time, and stops at the first failure, refusal or
exhausted quota; nothing is retried automatically. Earlier segments of this draft reach the
next request only as "本次候选稿" context, never as facts and never in any other task.
"""

import hashlib
import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from aiwebnovel.ai_writing.application.context import ChapterWritingContextBuilder
from aiwebnovel.ai_writing.application.models import GeneratedText, GenerationMessage
from aiwebnovel.ai_writing.application.services import CONTINUE_PROMPT, DATA_BOUNDARY
from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot, WorkflowProvider
from aiwebnovel.ai_writing.chapter_draft_models import (
    EVIDENCE_LIMIT,
    SEGMENT_MIN_CHARACTERS,
    ChapterDraft,
    ChapterDraftConflict,
    ChapterDraftConsentRequired,
    ChapterDraftInvalid,
    ChapterDraftSummary,
    ChapterDraftView,
    DraftFailure,
    DraftSegment,
    DraftStatus,
    FrozenContext,
)
from aiwebnovel.ai_writing.chapter_draft_persistence import has_quota, remaining, step_upper
from aiwebnovel.ai_writing.errors import AIContextChanged, AIProviderUnavailable
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.novel_structure.application.queries import GetChapterContentQuery
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.novel_structure.identifiers import ChapterId
from aiwebnovel.story_memory.models import snapshot_model
from aiwebnovel.usage.attribution import usage_attribution
from aiwebnovel.usage.budget import BudgetRefused, SendEstimate

Estimator = Callable[..., SendEstimate]

DRAFT_PROMPT = (
    "本次任务是章节候选稿:在作者确认的单章范围内，逐段续写当前章节。"
    "本次候选稿是本任务此前生成、作者尚未全部采用的候选段落，只用于保持衔接，"
    "不是已发生的正式正文，也不是已确认的事实。只推进紧接本次候选稿之后的下一小段，"
    "不要重复候选稿已有内容，不要把整章剩余情节压缩在一段内。"
)


class ChapterDraftStore(Protocol):
    def get(self, chapter_id: str, draft_id: str) -> tuple[ChapterDraft, int]: ...

    def list_recent(self, chapter_id: str, limit: int) -> tuple[tuple[ChapterDraft, int], ...]: ...

    def create(self, draft: ChapterDraft) -> tuple[ChapterDraft, int]: ...

    def claim(
        self, chapter_id: str, draft_id: str, expected_version: int | None
    ) -> tuple[ChapterDraft, int, DraftStatus]: ...

    def finish(self, chapter_id: str, draft_id: str, segment: DraftSegment) -> ChapterDraft: ...

    def fail(self, chapter_id: str, draft_id: str, failure: DraftFailure) -> ChapterDraft: ...

    def release_unsent(
        self, chapter_id: str, draft_id: str, previous: DraftStatus, error: str
    ) -> ChapterDraft: ...

    def recover_interrupted(self) -> None: ...

    def adopt(
        self,
        chapter_id: str,
        draft_id: str,
        segment_indexes: list[int] | None,
        idempotency_key: str,
    ) -> tuple[ChapterDraft, int]: ...


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _count(text: str) -> int:
    return sum(not character.isspace() for character in text)


def messages(draft: ChapterDraft) -> tuple[GenerationMessage, ...]:
    """The next segment's request; earlier segments appear only as labelled draft context."""
    limit = max(SEGMENT_MIN_CHARACTERS, step_upper(draft))
    prompt = CONTINUE_PROMPT + DRAFT_PROMPT
    if "chapter_plan" in draft.context.included_sources:
        prompt += "章节规划覆盖整章，目标字数指整章而非本次输出。"
    pending = [item.text for item in draft.segments if item.status == "pending"]
    return (
        GenerationMessage(
            "system",
            prompt
            + DATA_BOUNDARY
            + f"本段必须为{SEGMENT_MIN_CHARACTERS}至{limit}个非空白Unicode字符。",
        ),
        GenerationMessage("user", "小说上下文:\n" + draft.context.text),
        GenerationMessage("user", "额外创作要求:\n" + draft.instruction),
        GenerationMessage(
            "user",
            "本次候选稿(作者尚未采用,不是正式正文或事实):\n" + "\n\n".join(pending),
        ),
    )


def _view(draft: ChapterDraft, version: int) -> ChapterDraftView:
    requests, characters = remaining(draft)
    data = draft.model_dump(exclude={"context", "base_version"})
    return ChapterDraftView.model_validate(
        {
            **data,
            "version": version,
            "remaining_requests": requests,
            "remaining_characters": characters,
            "can_send": draft.status in ("ready", "failed") and has_quota(draft),
            "included_sources": draft.context.included_sources,
            "omitted_sources": draft.context.omitted_sources,
            "context_truncated": draft.context.truncated,
            "next_request_preview": "\n\n".join(
                f"[{item.role}]\n{item.content}" for item in messages(draft)
            ),
        }
    )


def _summary(draft: ChapterDraft, version: int) -> ChapterDraftSummary:
    return ChapterDraftSummary(
        id=draft.id,
        version=version,
        status=draft.status,
        segments=len(draft.segments),
        adopted=sum(item.status == "adopted" for item in draft.segments),
        generated_characters=draft.generated_characters,
        created_at=draft.created_at,
    )


class ChapterDraftService:
    def __init__(
        self,
        store: ChapterDraftStore,
        context_builder: ChapterWritingContextBuilder,
        structure: NovelStructureQueryService,
        provider: WorkflowProvider,
        model_reader: Callable[[str | None], ModelSnapshot],
        estimator: Estimator,
    ) -> None:
        self._store = store
        self._context_builder = context_builder
        self._structure = structure
        self._provider = provider
        self._models = model_reader
        self._estimator = estimator

    # ------------------------------------------------------------------ preparation

    def prepare(
        self,
        chapter_id: str,
        *,
        profile_id: str,
        instruction: str = "",
        max_segments: int = 10,
        max_output_characters: int = 3000,
        writing_job_id: str | None = None,
    ) -> ChapterDraftView:
        """Freeze the chapter's saved revision, context and quota; never calls a model."""
        chapter_id = str(ChapterId.parse(chapter_id))
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", profile_id):
            raise ChapterDraftInvalid
        before = self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))
        context = self._context_builder.build(chapter_id)
        after = self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))
        if before.current_revision_id != after.current_revision_id:
            raise AIContextChanged
        manifest = asdict(context.manifest)
        now = _now()
        draft = ChapterDraft(
            id=str(uuid4()),
            project_id="",  # Filled from the chapter inside the creating transaction.
            chapter_id=chapter_id,
            status="ready",
            model=snapshot_model(self._models(profile_id)),
            instruction=instruction,
            max_segments=max_segments,
            max_output_characters=max_output_characters,
            attempts=0,
            generated_characters=0,
            base_revision_id=before.current_revision_id,
            base_version=before.concurrency_version,
            current_revision_id=before.current_revision_id,
            current_version=before.concurrency_version,
            context=FrozenContext(
                text=context.text,
                sha256=hashlib.sha256(context.text.encode()).hexdigest(),
                included_sources=list(manifest["included_sources"]),
                omitted_sources=list(manifest["omitted_sources"]),
                truncated=bool(manifest["truncated"]),
                character_count=int(manifest["character_count"]),
            ),
            writing_job_id=writing_job_id,
            created_at=now,
            updated_at=now,
        )
        return _view(*self._store.create(draft))

    def get(self, chapter_id: str, draft_id: str) -> ChapterDraftView:
        return _view(*self._store.get(str(ChapterId.parse(chapter_id)), draft_id))

    def list_drafts(self, chapter_id: str) -> list[ChapterDraftSummary]:
        return [
            _summary(item, version)
            for item, version in self._store.list_recent(str(ChapterId.parse(chapter_id)), 20)
        ]

    def estimate(self, chapter_id: str, draft_id: str) -> SendEstimate:
        """Conservative cost of the next segment request; sends nothing."""
        chapter_id = str(ChapterId.parse(chapter_id))
        draft, _ = self._store.get(chapter_id, draft_id)
        return self._estimator(
            chapter_id=chapter_id,
            project_id=None,
            task_id=draft.id,
            profile_id=str(draft.model["id"]),
            messages=messages(draft),
        )

    # ------------------------------------------------------------------ explicit send

    @staticmethod
    def _model(draft: ChapterDraft) -> ModelSnapshot:
        return ModelSnapshot(
            id=str(draft.model["id"]),
            name=str(draft.model["name"]),
            kind=str(draft.model["kind"]),
            base_url=str(draft.model["base_url"]),
            model=str(draft.model["model"]),
            max_output_tokens=int(draft.model["max_output_tokens"]),
        )

    def _one(self, chapter_id: str, draft_id: str, expected_version: int | None) -> ChapterDraft:
        draft, _, previous = self._store.claim(chapter_id, draft_id, expected_version)
        limit = step_upper(draft)
        model = self._model(draft)
        try:
            with usage_attribution("chapter_draft", draft.id, chapter_id=chapter_id):
                generated = self._provider(model.id, messages(draft), limit, model)
        except BudgetRefused:
            # Refused locally before sending: the request is returned, nothing was charged.
            self._store.release_unsent(chapter_id, draft_id, previous, "BudgetRefused")
            raise
        except Exception as error:
            # No exception text or provider response is kept: either may contain secrets.
            code = (
                type(error).__name__ if isinstance(error, DomainError) else "AIProviderUnavailable"
            )
            self._store.fail(
                chapter_id,
                draft_id,
                DraftFailure(attempt=draft.attempts, error=code, at=_now()),
            )
            if isinstance(error, DomainError):
                raise
            raise AIProviderUnavailable from None
        text = generated.text if type(generated) is GeneratedText else ""
        count = _count(text)
        if not SEGMENT_MIN_CHARACTERS <= count <= limit:
            # The wrong-length reply is kept as evidence; the draft stops here.
            return self._store.fail(
                chapter_id,
                draft_id,
                DraftFailure(
                    attempt=draft.attempts,
                    error="ChapterDraftOutputInvalid",
                    evidence=text[:EVIDENCE_LIMIT],
                    evidence_truncated=len(text) > EVIDENCE_LIMIT,
                    at=_now(),
                ),
            )
        return self._store.finish(
            chapter_id,
            draft_id,
            DraftSegment(
                index=len(draft.segments),
                attempt=draft.attempts,
                text=text,
                characters=count,
                model=generated.model,
            ),
        )

    def send(
        self,
        chapter_id: str,
        draft_id: str,
        expected_version: int,
        cloud_consent: bool,
        segments: int = 1,
    ) -> ChapterDraftView:
        """Generate up to ``segments`` segments in order; stop at the first problem."""
        chapter_id = str(ChapterId.parse(chapter_id))
        draft, version = self._store.get(chapter_id, draft_id)
        if version != expected_version:
            raise ChapterDraftConflict
        if draft.model["kind"] == "cloud" and not cloud_consent:
            raise ChapterDraftConsentRequired
        produced = 0
        expected: int | None = expected_version
        while produced < segments:
            try:
                draft = self._one(chapter_id, draft_id, expected)
            except DomainError:
                # Refusal, stale chapter or provider failure: the failure is recorded on the
                # draft; segments already produced by this send are kept for the author.
                if produced == 0:
                    raise
                break
            expected = None
            if draft.status != "ready":
                break  # Failed (evidence kept, no automatic retry) or quota exhausted.
            produced += 1
        return self.get(chapter_id, draft_id)

    # ------------------------------------------------------------------ adoption

    def adopt(
        self,
        chapter_id: str,
        draft_id: str,
        segment_indexes: list[int] | None,
        idempotency_key: str,
    ) -> ChapterDraftView:
        chapter_id = str(ChapterId.parse(chapter_id))
        return _view(*self._store.adopt(chapter_id, draft_id, segment_indexes, idempotency_key))

    def recover_interrupted(self) -> None:
        """Call once during exclusive application startup, never per request."""
        self._store.recover_interrupted()

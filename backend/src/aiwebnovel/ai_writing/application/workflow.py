"""Explicit, bounded generation; only author adoption writes manuscript revisions."""

import hashlib
import re
from collections.abc import Callable
from uuid import uuid4

from aiwebnovel.ai_writing.application.context import ChapterWritingContextBuilder
from aiwebnovel.ai_writing.application.models import GeneratedText, GenerationMessage, validate_text
from aiwebnovel.ai_writing.application.services import (
    CONTINUE_PROMPT,
    DATA_BOUNDARY,
    REWRITE_PROMPT,
)
from aiwebnovel.ai_writing.application.workflow_models import (
    ContextPack,
    ModelSnapshot,
    Operation,
    WorkflowOutputInvalid,
    WorkflowProvider,
    WorkflowRepository,
    WorkflowRun,
)
from aiwebnovel.ai_writing.errors import AIContextChanged, AIProviderInvalidResponse, InvalidAIInput
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.novel_structure.application.queries import GetChapterContentQuery
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.novel_structure.identifiers import ChapterId


class AIWorkflowService:
    def __init__(
        self,
        repository: WorkflowRepository,
        context_builder: ChapterWritingContextBuilder,
        structure: NovelStructureQueryService,
        provider: WorkflowProvider,
        model_reader: Callable[[str | None], ModelSnapshot] | None = None,
    ) -> None:
        self._repository = repository
        self._context_builder = context_builder
        self._structure = structure
        self._provider = provider
        self._model_reader = model_reader

    def create(
        self,
        chapter_id: str,
        *,
        operation: Operation = "continue",
        instruction: str = "",
        profile_id: str | None = None,
        selected_text: str = "",
        selection_start: int | None = None,
        selection_end: int | None = None,
        max_steps: int = 5,
        max_output_characters: int = 1500,
    ) -> WorkflowRun:
        chapter_id = str(ChapterId.parse(chapter_id))
        instruction = validate_text(instruction, limit=4000, allow_empty=True)
        selected_text = validate_text(selected_text, limit=50_000, allow_empty=True)
        if (
            operation not in ("continue", "rewrite")
            or type(max_steps) is not int
            or not 1 <= max_steps <= 10
            or type(max_output_characters) is not int
            or not 200 <= max_output_characters <= 3000
            or (profile_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", profile_id))
            or (operation == "continue" and selected_text)
            or (operation == "rewrite" and (not selected_text.strip() or max_steps != 1))
        ):
            raise InvalidAIInput
        before = self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))
        context = self._context_builder.build(chapter_id)
        after = self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))
        if before.current_revision_id != after.current_revision_id:
            raise AIContextChanged
        if operation == "rewrite":
            if (
                type(selection_start) is not int
                or type(selection_end) is not int
                or selection_start < 0
                or selection_end <= selection_start
            ):
                raise InvalidAIInput
            encoded = before.content.encode("utf-16-le")
            try:
                target = encoded[selection_start * 2 : selection_end * 2].decode("utf-16-le")
            except UnicodeDecodeError:
                raise InvalidAIInput from None
            if selection_end * 2 > len(encoded) or target != selected_text:
                raise InvalidAIInput
        elif selection_start is not None or selection_end is not None:
            raise InvalidAIInput
        return self._repository.create(
            WorkflowRun(
                run_id=str(uuid4()),
                chapter_id=chapter_id,
                operation=operation,
                status="ready",
                base_revision_id=before.current_revision_id,
                base_version=before.concurrency_version,
                current_revision_id=before.current_revision_id,
                current_version=before.concurrency_version,
                instruction=instruction,
                profile_id=profile_id,
                selected_text=selected_text,
                max_steps=max_steps,
                selection_start=selection_start,
                selection_end=selection_end,
                max_output_characters=max_output_characters,
                generated_steps=0,
                generated_characters=0,
                context=ContextPack(
                    context.text,
                    hashlib.sha256(context.text.encode()).hexdigest(),
                    context.manifest,
                ),
                candidates=(),
                last_error=None,
                model_snapshot=self._model_reader(profile_id) if self._model_reader else None,
            )
        )

    def get(self, chapter_id: str, run_id: str) -> WorkflowRun:
        return self._repository.get(str(ChapterId.parse(chapter_id)), run_id)

    def list(self, chapter_id: str) -> tuple[WorkflowRun, ...]:
        return self._repository.list(str(ChapterId.parse(chapter_id)))

    def generate(self, chapter_id: str, run_id: str) -> WorkflowRun:
        chapter_id = str(ChapterId.parse(chapter_id))
        run = self._repository.claim(chapter_id, run_id)
        limit = min(300, run.max_output_characters - run.generated_characters)
        prompt = CONTINUE_PROMPT if run.operation == "continue" else REWRITE_PROMPT
        messages: tuple[GenerationMessage, ...] = (
            GenerationMessage(
                "system", prompt + DATA_BOUNDARY + f"本段必须为200至{limit}个非空白Unicode字符。"
            ),
            GenerationMessage("user", "小说上下文:\n" + run.context.text),
            GenerationMessage("user", "额外创作要求:\n" + run.instruction),
            GenerationMessage(
                "user",
                "本轮已有候选:\n"
                + "\n\n".join(c.text for c in run.candidates if c.status != "discarded"),
            ),
        )
        if run.operation == "rewrite":
            messages += (GenerationMessage("user", "待改写text:\n" + run.selected_text),)
        try:
            generated = self._provider(run.profile_id, messages, limit, run.model_snapshot)
            if type(generated) is not GeneratedText:
                raise AIProviderInvalidResponse
            count = sum(not character.isspace() for character in generated.text)
            if not 200 <= count <= limit:
                raise WorkflowOutputInvalid
            return self._repository.finish(chapter_id, run_id, generated, count)
        except DomainError as error:
            self._repository.fail(chapter_id, run_id, type(error).__name__)
            raise
        except Exception:
            # No exception text or provider response is persisted: either may contain secrets.
            self._repository.fail(chapter_id, run_id, "AI_PROVIDER_UNAVAILABLE")
            raise

    def pause(self, chapter_id: str, run_id: str) -> WorkflowRun:
        return self._repository.transition(str(ChapterId.parse(chapter_id)), run_id, resume=False)

    def resume(self, chapter_id: str, run_id: str) -> WorkflowRun:
        return self._repository.transition(str(ChapterId.parse(chapter_id)), run_id, resume=True)

    def adopt(
        self, chapter_id: str, candidate_id: str, expected_version: int, idempotency_key: str
    ) -> WorkflowRun:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", idempotency_key):
            raise InvalidAIInput
        return self._repository.adopt(
            str(ChapterId.parse(chapter_id)), candidate_id, expected_version, idempotency_key
        )

    def discard(self, chapter_id: str, candidate_id: str) -> WorkflowRun:
        return self._repository.discard(str(ChapterId.parse(chapter_id)), candidate_id)

    def recover_interrupted(self) -> None:
        """Call once during exclusive application startup, never per request."""
        self._repository.recover_interrupted()

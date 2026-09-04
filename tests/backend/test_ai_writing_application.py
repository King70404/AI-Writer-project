"""Generation requests, strict inputs, privacy, and zero write orchestration."""

from unittest.mock import Mock

import pytest
from tests.backend.ai_writing_support import CHAPTER, FakeProvider, sources

from aiwebnovel.ai_writing.application.models import GeneratedText, validate_text
from aiwebnovel.ai_writing.application.services import AIWritingService
from aiwebnovel.ai_writing.errors import (
    AIProviderInvalidResponse,
    AIProviderNotConfigured,
    AIProviderTimeout,
    AIProviderUnavailable,
    InvalidAIInput,
)
from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.novel_structure.errors import ChapterNotFound


@pytest.mark.parametrize("operation", ["continue", "rewrite"])
def test_candidate_prompts_instruction_and_manifest_without_writes(operation: str) -> None:
    s = sources()
    provider = FakeProvider()
    service = AIWritingService(s.builder, provider)
    result = (
        service.continue_chapter(CHAPTER, "  保持紧凑  ")
        if operation == "continue"
        else service.rewrite_chapter_text(CHAPTER, "原文\r\n第二段", " 保持紧凑 ")
    )
    assert result.operation == operation and result.text == "候选正文\n第二段"
    assert result.context == s.builder.build(CHAPTER).manifest
    assert len(provider.calls) == 1
    messages = provider.calls[0]
    assert messages[0].role == "system"
    assert messages[2].content.endswith("\n保持紧凑")
    if operation == "rewrite":
        assert messages[-1].content.endswith("原文\n第二段")
        assert "不要继续后续情节" in messages[0].content
    else:
        assert len(messages) == 3 and "不要重复大段已有正文" in messages[0].content
    assert all(call[0].startswith(("get_", "list_")) for call in s.structure.mock_calls)


@pytest.mark.parametrize(
    "error_type",
    [AIProviderNotConfigured, AIProviderTimeout, AIProviderUnavailable, AIProviderInvalidResponse],
)
def test_provider_failure_propagates_without_retry(error_type: type[Exception]) -> None:
    error = error_type()
    p = FakeProvider(error)
    service = AIWritingService(sources().builder, p)
    with pytest.raises(error_type) as caught:
        service.continue_chapter(CHAPTER)
    assert caught.value is error and len(p.calls) == 1


def test_missing_chapter_precedes_provider_even_when_not_configured() -> None:
    s = sources()
    s.structure.get_chapter.side_effect = ChapterNotFound()
    p = FakeProvider(AIProviderNotConfigured())
    with pytest.raises(ChapterNotFound):
        AIWritingService(s.builder, p).continue_chapter(CHAPTER)
    assert p.calls == []


@pytest.mark.parametrize(
    "value",
    [None, False, 1, [], "x" * 4001, "bad\x00"],
    ids=["none", "bool", "int", "list", "long", "control"],
)
def test_invalid_instruction_has_no_external_side_effect(value: object) -> None:
    s = sources()
    p = FakeProvider()
    with pytest.raises(InvalidAIInput):
        AIWritingService(s.builder, p).continue_chapter(CHAPTER, value)
    s.structure.get_chapter.assert_not_called()
    assert p.calls == []


@pytest.mark.parametrize(
    "value",
    ["", "  ", None, False, "x" * 50001, "bad\x00"],
    ids=["empty", "blank", "none", "bool", "long", "control"],
)
def test_invalid_rewrite_has_no_side_effect(value: object) -> None:
    s = sources()
    p = FakeProvider()
    with pytest.raises(InvalidAIInput):
        AIWritingService(s.builder, p).rewrite_chapter_text(CHAPTER, value)
    s.structure.get_chapter.assert_not_called()
    assert p.calls == []


@pytest.mark.parametrize("value", [None, 1, False, "bad", "CHP_00000000000000000000000000"])
def test_invalid_id_has_no_side_effect(value: object) -> None:
    s = sources()
    p = FakeProvider()
    with pytest.raises(InvalidDomainIdentifier):
        AIWritingService(s.builder, p).continue_chapter(value)
    assert p.calls == []


@pytest.mark.parametrize(
    "text",
    ["", " ", None, 1, "x" * 50001, "AI_WRITING_CANARY\x00"],
    ids=["empty", "blank", "none", "int", "long", "control"],
)
def test_invalid_generated_text_safe(text: object) -> None:
    with pytest.raises(AIProviderInvalidResponse) as caught:
        GeneratedText(text, "model")
    assert "AI_WRITING_CANARY" not in str(caught.value)


@pytest.mark.parametrize("model", [None, 1, "", "model\n", "model with spaces"])
def test_invalid_generated_model_safe(model: object) -> None:
    with pytest.raises(AIProviderInvalidResponse):
        GeneratedText("text", model)


def test_provider_contract_must_return_generated_text() -> None:
    p = Mock()
    p.generate.return_value = "AI_WRITING_CANARY"
    with pytest.raises(AIProviderInvalidResponse) as caught:
        AIWritingService(sources().builder, p).continue_chapter(CHAPTER)
    assert "AI_WRITING_CANARY" not in str(caught.value)
    assert validate_text("\t\r\n", limit=3, allow_empty=True) == "\t\n"


def test_unpaired_surrogate_cannot_enter_request_or_candidate() -> None:
    with pytest.raises(InvalidAIInput):
        validate_text("\ud800", limit=10)
    with pytest.raises(AIProviderInvalidResponse):
        GeneratedText("\udfff", "model")

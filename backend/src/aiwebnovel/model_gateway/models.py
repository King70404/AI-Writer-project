"""Public model settings contain presence flags, never credential values."""

import re
from dataclasses import dataclass
from typing import Literal

from aiwebnovel.ai_writing.application.models import MODEL_NAME
from aiwebnovel.model_gateway.errors import InvalidModelProfile

MAX_OUTPUT_TOKENS = 16_384
PROFILE_ID = re.compile(r"(?:default-local|[0-9a-f]{32})\Z")


@dataclass(frozen=True, slots=True)
class ModelProfile:
    id: str
    name: str
    kind: Literal["local", "cloud"]
    base_url: str
    model: str
    max_output_tokens: int
    has_key: bool


def validate_profile(profile: ModelProfile) -> None:
    if (
        type(profile.id) is not str
        or not PROFILE_ID.fullmatch(profile.id)
        or type(profile.name) is not str
        or not profile.name.strip()
        or len(profile.name) > 100
        or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in profile.name)
        or profile.kind not in {"local", "cloud"}
        or type(profile.model) is not str
        or not MODEL_NAME.fullmatch(profile.model)
        or type(profile.max_output_tokens) is not int
        or not 1 <= profile.max_output_tokens <= MAX_OUTPUT_TOKENS
        or type(profile.has_key) is not bool
    ):
        raise InvalidModelProfile


def validate_key(value: str) -> None:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 4096
        or any(not 33 <= ord(char) <= 126 for char in value)
    ):
        raise InvalidModelProfile

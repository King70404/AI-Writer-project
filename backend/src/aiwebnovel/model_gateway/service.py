"""Atomic profile settings and separate user-protected credentials per data root."""

import json
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

from aiwebnovel.ai_writing.application.models import GeneratedText, GenerationMessage
from aiwebnovel.ai_writing.errors import AIContextChanged, AIProviderNotConfigured, InvalidAIInput
from aiwebnovel.core.config import normalize_data_root
from aiwebnovel.model_gateway.credentials import (
    CredentialProtector,
    WindowsDPAPIProtector,
    credential_scope,
)
from aiwebnovel.model_gateway.errors import (
    InvalidModelProfile,
    ModelConfigurationUnavailable,
    ModelCredentialUnavailable,
    ModelProfileNotFound,
)
from aiwebnovel.model_gateway.models import ModelProfile, validate_key, validate_profile
from aiwebnovel.model_gateway.provider import endpoint_for, generate_text

MAX_PROFILES = 32
MAX_CONFIG_BYTES = 131_072
_KEY_REF = re.compile(r"[0-9a-f]{32}\Z")


@dataclass(frozen=True, slots=True)
class _Record:
    profile: ModelProfile
    key_ref: str | None = None


class ModelGatewayService:
    def __init__(
        self,
        data_root: Path,
        *,
        default_base_url: str | None = None,
        default_model: str | None = None,
        protector: CredentialProtector | None = None,
    ) -> None:
        self._root = normalize_data_root(data_root)
        self._directory = self._root / "config" / "model-gateway"
        self._protector = protector if protector is not None else WindowsDPAPIProtector()
        self._lock = RLock()
        self._default: tuple[_Record, ...] = ()
        # Invalid optional environment settings must not prevent manual writing.
        if default_base_url and default_model:
            try:
                profile = self._make_profile(
                    "default-local",
                    "默认本地模型",
                    "local",
                    default_base_url,
                    default_model,
                    2048,
                    False,
                )
                self._default = (_Record(profile),)
            except InvalidModelProfile:
                pass

    @staticmethod
    def _make_profile(
        profile_id: str,
        name: str,
        kind: Literal["local", "cloud"],
        base_url: str,
        model: str,
        max_output_tokens: int,
        has_key: bool,
    ) -> ModelProfile:
        profile = ModelProfile(profile_id, name, kind, base_url, model, max_output_tokens, has_key)
        validate_profile(profile)
        endpoint_for(kind, base_url)
        return profile

    def _path(self, filename: str) -> Path:
        target = self._directory / filename
        # Do not follow a redirected config/key directory out of the chosen data root.
        for path in (self._root, self._root / "config", self._directory, target):
            if path.is_symlink() or path.is_junction():
                raise ModelConfigurationUnavailable
        return target

    def _read(self) -> tuple[_Record, ...]:
        try:
            path = self._path("profiles.json")
            if not path.exists():
                return self._default
            with path.open("rb") as stream:
                data = stream.read(MAX_CONFIG_BYTES + 1)
            if len(data) > MAX_CONFIG_BYTES:
                raise ModelConfigurationUnavailable
            decoded = json.loads(data)
            if (
                type(decoded) is not dict
                or set(decoded) != {"version", "profiles"}
                or decoded["version"] != 1
                or type(decoded["profiles"]) is not list
                or len(decoded["profiles"]) > MAX_PROFILES
            ):
                raise ModelConfigurationUnavailable
            records = []
            seen: set[str] = set()
            for item in decoded["profiles"]:
                if type(item) is not dict or set(item) != {
                    "id",
                    "name",
                    "kind",
                    "base_url",
                    "model",
                    "max_output_tokens",
                    "key_ref",
                }:
                    raise ModelConfigurationUnavailable
                key_ref = item["key_ref"]
                if key_ref is not None and (
                    type(key_ref) is not str or not _KEY_REF.fullmatch(key_ref)
                ):
                    raise ModelConfigurationUnavailable
                profile = self._make_profile(
                    item["id"],
                    item["name"],
                    item["kind"],
                    item["base_url"],
                    item["model"],
                    item["max_output_tokens"],
                    key_ref is not None,
                )
                if profile.id in seen or (profile.kind == "local" and key_ref is not None):
                    raise ModelConfigurationUnavailable
                seen.add(profile.id)
                records.append(_Record(profile, key_ref))
            return tuple(records)
        except (OSError, ValueError, TypeError, RecursionError, InvalidModelProfile):
            raise ModelConfigurationUnavailable from None

    def _atomic_write(self, filename: str, value: bytes) -> None:
        temporary: Path | None = None
        try:
            target = self._path(filename)
            self._directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self._directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except OSError:
            raise ModelConfigurationUnavailable from None
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def _write(self, records: tuple[_Record, ...]) -> None:
        profiles = []
        for record in records:
            profile = asdict(record.profile)
            del profile["has_key"]
            profile["key_ref"] = record.key_ref
            profiles.append(profile)
        self._atomic_write(
            "profiles.json",
            json.dumps({"version": 1, "profiles": profiles}, ensure_ascii=True).encode(),
        )

    def _remove_key(self, key_ref: str | None) -> None:
        if key_ref is not None:
            try:
                self._path(f"{key_ref}.key").unlink(missing_ok=True)
            except OSError:
                raise ModelConfigurationUnavailable from None

    def _protect_key(self, profile_id: str, api_key: str) -> str:
        validate_key(api_key)
        protected = self._protector.protect(
            api_key.encode("ascii"), credential_scope(self._root, profile_id)
        )
        if not protected or len(protected) > 16_384:
            raise ModelCredentialUnavailable
        key_ref = uuid4().hex
        self._atomic_write(f"{key_ref}.key", protected)
        return key_ref

    def _load_key(self, record: _Record) -> str | None:
        if record.key_ref is None:
            return None
        try:
            with self._path(f"{record.key_ref}.key").open("rb") as stream:
                protected = stream.read(16_385)
            if not protected or len(protected) > 16_384:
                raise ModelCredentialUnavailable
            value = self._protector.unprotect(
                protected, credential_scope(self._root, record.profile.id)
            ).decode("ascii")
            validate_key(value)
            return value
        except (OSError, UnicodeError, InvalidModelProfile):
            raise ModelCredentialUnavailable from None

    def list_profiles(self) -> tuple[ModelProfile, ...]:
        with self._lock:
            return tuple(record.profile for record in self._read())

    def get_profile(self, profile_id: str) -> ModelProfile:
        with self._lock:
            return self._find(self._read(), profile_id).profile

    @staticmethod
    def _find(records: tuple[_Record, ...], profile_id: str) -> _Record:
        for record in records:
            if record.profile.id == profile_id:
                return record
        raise ModelProfileNotFound

    def create_profile(
        self,
        *,
        name: str,
        kind: Literal["local", "cloud"],
        base_url: str,
        model: str,
        max_output_tokens: int = 2048,
        api_key: str | None = None,
    ) -> ModelProfile:
        profile = self._make_profile(
            uuid4().hex, name, kind, base_url, model, max_output_tokens, api_key is not None
        )
        if kind == "local" and api_key is not None:
            raise InvalidModelProfile
        with self._lock:
            records = self._read()
            if len(records) >= MAX_PROFILES:
                raise InvalidModelProfile
            key_ref = self._protect_key(profile.id, api_key) if api_key is not None else None
            try:
                self._write((*records, _Record(profile, key_ref)))
            except ModelConfigurationUnavailable:
                self._remove_key(key_ref)
                raise
            return profile

    def update_profile(
        self,
        profile_id: str,
        *,
        name: str,
        kind: Literal["local", "cloud"],
        base_url: str,
        model: str,
        max_output_tokens: int = 2048,
        api_key: str | None = None,
        clear_key: bool = False,
    ) -> ModelProfile:
        profile = self._make_profile(
            profile_id, name, kind, base_url, model, max_output_tokens, False
        )
        if (api_key is not None and (clear_key or kind == "local")) or type(clear_key) is not bool:
            raise InvalidModelProfile
        with self._lock:
            records = self._read()
            previous = self._find(records, profile_id)
            key_ref = None if clear_key or kind == "local" else previous.key_ref
            # A stored key must not silently move to a different provider endpoint.
            if (
                key_ref is not None
                and api_key is None
                and endpoint_for(kind, base_url)
                != endpoint_for(previous.profile.kind, previous.profile.base_url)
            ):
                raise InvalidModelProfile
            if api_key is not None:
                key_ref = self._protect_key(profile_id, api_key)
            profile = replace(profile, has_key=key_ref is not None)
            updated = tuple(
                _Record(profile, key_ref) if item.profile.id == profile_id else item
                for item in records
            )
            try:
                self._write(updated)
            except ModelConfigurationUnavailable:
                if api_key is not None:
                    self._remove_key(key_ref)
                raise
            if previous.key_ref != key_ref:
                self._remove_key(previous.key_ref)
            return profile

    def remove_profile(self, profile_id: str) -> None:
        with self._lock:
            records = self._read()
            previous = self._find(records, profile_id)
            self._write(tuple(item for item in records if item.profile.id != profile_id))
            self._remove_key(previous.key_ref)

    def generate(
        self,
        profile_id: str,
        messages: tuple[GenerationMessage, ...],
        *,
        max_output_tokens: int | None = None,
        expected_configuration: tuple[str, str, str, int] | None = None,
        before_send: Callable[[ModelProfile], None] | None = None,
    ) -> GeneratedText:
        """Generate once. ``before_send`` runs after every local check, right before
        the provider request, so callers can meter exactly the requests that go out."""
        with self._lock:
            record = self._find(self._read(), profile_id)
            if expected_configuration is not None and expected_configuration != (
                record.profile.kind,
                record.profile.base_url,
                record.profile.model,
                record.profile.max_output_tokens,
            ):
                raise AIContextChanged
            key = self._load_key(record)
        if record.profile.kind == "cloud" and key is None:
            raise AIProviderNotConfigured
        limit = record.profile.max_output_tokens if max_output_tokens is None else max_output_tokens
        if type(limit) is not int or not 1 <= limit <= record.profile.max_output_tokens:
            raise InvalidAIInput
        if before_send is not None:
            before_send(record.profile)
        return generate_text(record.profile, messages, api_key=key, max_output_tokens=limit)

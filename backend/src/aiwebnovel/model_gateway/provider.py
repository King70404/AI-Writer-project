"""Bounded OpenAI-compatible transport; no redirects, proxies, or private cloud peers."""

import http.client
import ipaddress
import json
import re
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

from aiwebnovel.ai_writing.application.models import (
    GeneratedText,
    GenerationMessage,
    ProviderUsage,
    parse_provider_usage,
)
from aiwebnovel.ai_writing.errors import (
    AIProviderAccessDenied,
    AIProviderAuthFailed,
    AIProviderConfigurationInvalid,
    AIProviderEndpointInvalid,
    AIProviderInvalidResponse,
    AIProviderPaymentRequired,
    AIProviderRateLimited,
    AIProviderRequestRejected,
    AIProviderTimeout,
    AIProviderUnavailable,
    InvalidAIInput,
)
from aiwebnovel.ai_writing.provider import (
    MAX_RESPONSE_BYTES,
    PROVIDER_TIMEOUT_SECONDS,
    local_endpoint,
)
from aiwebnovel.model_gateway.errors import InvalidModelProfile
from aiwebnovel.model_gateway.models import ModelProfile

MAX_PROMPT_CHARACTERS = 100_000
_HOST = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\Z")


@dataclass(frozen=True, slots=True)
class Endpoint:
    scheme: str
    host: str
    port: int
    path: str


def _public_address(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
        return parsed.is_global and not parsed.is_multicast
    except ValueError:
        return False


def endpoint_for(kind: str, base_url: str) -> Endpoint:
    if type(base_url) is not str or len(base_url) > 2048:
        raise InvalidModelProfile
    if kind == "local":
        try:
            return Endpoint(*local_endpoint(base_url))
        except AIProviderConfigurationInvalid:
            raise InvalidModelProfile from None
    if kind != "cloud":
        raise InvalidModelProfile
    try:
        url = urlsplit(base_url)
        host = url.hostname or ""
        if (
            url.scheme != "https"
            or not host
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(char.isspace() or ord(char) < 32 for char in base_url)
            or not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)*/?", url.path)
            or (url.port is not None and not 1 <= url.port <= 65535)
        ):
            raise InvalidModelProfile
        try:
            ipaddress.ip_address(host)
        except ValueError:
            labels = host.split(".")
            if (
                len(labels) < 2
                or len(host) > 253
                or not all(_HOST.fullmatch(label) for label in labels)
                or labels[-1].isdigit()
                or labels[-1] in {"localhost", "local", "internal", "test", "invalid"}
            ):
                raise InvalidModelProfile from None
        else:
            if not _public_address(host):
                raise InvalidModelProfile
        path = url.path.rstrip("/")
        if not path.endswith("/chat/completions"):
            path += "/chat/completions"
        return Endpoint("https", host, url.port or 443, path)
    except ValueError:
        raise InvalidModelProfile from None


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, *, timeout: int) -> None:
        self._tls_context = ssl.create_default_context()
        super().__init__(host, port, timeout=timeout, context=self._tls_context)

    def connect(self) -> None:
        # Resolve exactly once, reject mixed public/private DNS answers, and connect
        # to the validated numeric address while verifying TLS against the DNS name.
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        if not addresses or any(not _public_address(str(entry[4][0])) for entry in addresses):
            raise AIProviderUnavailable
        family, socktype, proto, _, address = addresses[0]
        connection = socket.socket(family, socktype, proto)
        try:
            connection.settimeout(PROVIDER_TIMEOUT_SECONDS)
            connection.connect(address)
            self.sock = self._tls_context.wrap_socket(connection, server_hostname=self.host)
        except (OSError, http.client.HTTPException):
            connection.close()
            raise


def generate_text(
    profile: ModelProfile,
    messages: tuple[GenerationMessage, ...],
    *,
    api_key: str | None,
    max_output_tokens: int,
) -> GeneratedText:
    if (
        not messages
        or len(messages) > 32
        or any(
            item.role not in {"system", "user"} or type(item.content) is not str
            for item in messages
        )
        or sum(len(item.content) for item in messages) > MAX_PROMPT_CHARACTERS
        or type(max_output_tokens) is not int
        or not 1 <= max_output_tokens <= profile.max_output_tokens
    ):
        raise InvalidAIInput
    endpoint = endpoint_for(profile.kind, profile.base_url)
    connection: http.client.HTTPConnection
    if profile.kind == "cloud":
        connection = _PublicHTTPSConnection(
            endpoint.host, endpoint.port, timeout=PROVIDER_TIMEOUT_SECONDS
        )
    else:
        factory = (
            http.client.HTTPSConnection
            if endpoint.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = factory(endpoint.host, endpoint.port, timeout=PROVIDER_TIMEOUT_SECONDS)
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        payload = json.dumps(
            {
                "model": profile.model,
                "messages": [{"role": item.role, "content": item.content} for item in messages],
                "max_tokens": max_output_tokens,
                "stream": False,
            },
            ensure_ascii=True,
        ).encode("utf-8")
        connection.request("POST", endpoint.path, body=payload, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            # Only status codes cross the boundary: upstream bodies can contain keys
            # or submitted prose. These are provider failures, not local session errors.
            failures = {
                400: AIProviderRequestRejected,
                401: AIProviderAuthFailed,
                402: AIProviderPaymentRequired,
                403: AIProviderAccessDenied,
                404: AIProviderEndpointInvalid,
                405: AIProviderEndpointInvalid,
                422: AIProviderRequestRejected,
                429: AIProviderRateLimited,
            }
            if failure := failures.get(response.status):
                raise failure
            raise AIProviderUnavailable
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise AIProviderInvalidResponse
        try:
            data = json.loads(raw)
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError, RecursionError):
            raise AIProviderInvalidResponse from None
        return GeneratedText(text, profile.model, parse_provider_usage(data))
    except TimeoutError:
        raise AIProviderTimeout from None
    except (OSError, http.client.HTTPException):
        raise AIProviderUnavailable from None
    finally:
        connection.close()


# -- embeddings (C-4 semantic index) -----------------------------------------------------

MAX_EMBEDDING_INPUTS = 32
MAX_EMBEDDING_CHARACTERS = 24_000
MAX_EMBEDDING_DIMENSIONS = 8192


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Vectors in input order and the provider's usage report exactly as given."""

    vectors: tuple[tuple[float, ...], ...]
    model: str
    usage: ProviderUsage | None


def embeddings_endpoint(kind: str, base_url: str) -> Endpoint:
    """The OpenAI-compatible ``/embeddings`` path beside ``/chat/completions``."""
    endpoint = endpoint_for(kind, base_url)
    return Endpoint(
        endpoint.scheme,
        endpoint.host,
        endpoint.port,
        endpoint.path.removesuffix("/chat/completions") + "/embeddings",
    )


def _vector(value: object) -> tuple[float, ...]:
    if (
        type(value) is not list
        or not 1 <= len(value) <= MAX_EMBEDDING_DIMENSIONS
        or any(type(item) not in (int, float) for item in value)
    ):
        raise AIProviderInvalidResponse
    vector = tuple(float(item) for item in value)
    if any(item != item or item in (float("inf"), float("-inf")) for item in vector):
        raise AIProviderInvalidResponse
    return vector


def parse_embeddings(data: object, expected: int) -> tuple[tuple[float, ...], ...]:
    try:
        assert isinstance(data, dict)
        items = data["data"]
        if type(items) is not list or len(items) != expected:
            raise AIProviderInvalidResponse
        ordered: dict[int, tuple[float, ...]] = {}
        for position, item in enumerate(items):
            index = item.get("index", position)
            if type(index) is not int or not 0 <= index < expected or index in ordered:
                raise AIProviderInvalidResponse
            ordered[index] = _vector(item["embedding"])
    except (AssertionError, KeyError, TypeError, AttributeError):
        raise AIProviderInvalidResponse from None
    vectors = tuple(ordered[index] for index in range(expected))
    if len({len(vector) for vector in vectors}) != 1:
        raise AIProviderInvalidResponse
    return vectors


def embed_texts(
    profile: ModelProfile,
    texts: tuple[str, ...],
    *,
    api_key: str | None,
) -> EmbeddingResult:
    """One bounded ``/embeddings`` request; same SSRF, proxy and error rules as chat."""
    if (
        profile.purpose != "embedding"
        or not texts
        or len(texts) > MAX_EMBEDDING_INPUTS
        or any(type(text) is not str or not text for text in texts)
        or sum(len(text) for text in texts) > MAX_EMBEDDING_CHARACTERS
    ):
        raise InvalidAIInput
    endpoint = embeddings_endpoint(profile.kind, profile.base_url)
    connection: http.client.HTTPConnection
    if profile.kind == "cloud":
        connection = _PublicHTTPSConnection(
            endpoint.host, endpoint.port, timeout=PROVIDER_TIMEOUT_SECONDS
        )
    else:
        factory = (
            http.client.HTTPSConnection
            if endpoint.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = factory(endpoint.host, endpoint.port, timeout=PROVIDER_TIMEOUT_SECONDS)
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        payload = json.dumps(
            {"model": profile.model, "input": list(texts)}, ensure_ascii=True
        ).encode("utf-8")
        connection.request("POST", endpoint.path, body=payload, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            failures = {
                400: AIProviderRequestRejected,
                401: AIProviderAuthFailed,
                402: AIProviderPaymentRequired,
                403: AIProviderAccessDenied,
                404: AIProviderEndpointInvalid,
                405: AIProviderEndpointInvalid,
                422: AIProviderRequestRejected,
                429: AIProviderRateLimited,
            }
            if failure := failures.get(response.status):
                raise failure
            raise AIProviderUnavailable
        raw = response.read(MAX_EMBEDDING_RESPONSE_BYTES + 1)
        if len(raw) > MAX_EMBEDDING_RESPONSE_BYTES:
            raise AIProviderInvalidResponse
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            raise AIProviderInvalidResponse from None
        return EmbeddingResult(
            parse_embeddings(data, len(texts)), profile.model, parse_provider_usage(data)
        )
    except TimeoutError:
        raise AIProviderTimeout from None
    except (OSError, http.client.HTTPException):
        raise AIProviderUnavailable from None
    finally:
        connection.close()


# 32 vectors x 8192 dimensions of JSON numbers fit comfortably; larger replies are refused.
MAX_EMBEDDING_RESPONSE_BYTES = 16 * 1024 * 1024

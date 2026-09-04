"""Standard-library local HTTP adapter: no proxies, redirects, keys, or cloud hosts."""

import http.client
import json
import re
from urllib.parse import urlsplit

from aiwebnovel.ai_writing.application.models import MODEL_NAME, GeneratedText, GenerationMessage
from aiwebnovel.ai_writing.errors import (
    AIProviderConfigurationInvalid,
    AIProviderInvalidResponse,
    AIProviderNotConfigured,
    AIProviderTimeout,
    AIProviderUnavailable,
)

PROVIDER_TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 1_048_576


def local_endpoint(base_url: str) -> tuple[str, str, int, str]:
    try:
        url = urlsplit(base_url)
        if (
            url.scheme not in {"http", "https"}
            or url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or url.port is None
            or url.port == 0
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(character.isspace() or ord(character) < 32 for character in base_url)
            or not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)*/?", url.path)
        ):
            raise AIProviderConfigurationInvalid
        # Pin localhost to numeric loopback: neither proxies nor DNS can redirect prose.
        host = "127.0.0.1" if url.hostname == "localhost" else url.hostname
        return url.scheme, host, url.port, url.path.rstrip("/") + "/chat/completions"
    except ValueError:
        raise AIProviderConfigurationInvalid from None


class LocalOpenAICompatibleProvider:
    def __init__(self, base_url: str | None, model: str | None) -> None:
        self._base_url = base_url
        self._model = model

    def generate(self, messages: tuple[GenerationMessage, ...]) -> GeneratedText:
        if not self._base_url or not self._model:
            raise AIProviderNotConfigured
        if not MODEL_NAME.fullmatch(self._model):
            raise AIProviderConfigurationInvalid
        scheme, host, port, path = local_endpoint(self._base_url)
        factory = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
        connection = factory(host, port, timeout=PROVIDER_TIMEOUT_SECONDS)
        try:
            payload = json.dumps(
                {
                    "model": self._model,
                    "messages": [{"role": item.role, "content": item.content} for item in messages],
                    "stream": False,
                },
                ensure_ascii=True,
            ).encode("utf-8")
            connection.request(
                "POST", path, body=payload, headers={"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            if response.status != 200:
                raise AIProviderUnavailable
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise AIProviderInvalidResponse
            try:
                data = json.loads(raw)
                text = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError, RecursionError):
                raise AIProviderInvalidResponse from None
            return GeneratedText(text, self._model)
        except TimeoutError:
            raise AIProviderTimeout from None
        except (OSError, http.client.HTTPException):
            raise AIProviderUnavailable from None
        finally:
            connection.close()

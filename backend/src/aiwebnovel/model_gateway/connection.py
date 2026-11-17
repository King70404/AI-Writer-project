"""Explicit, bounded metadata checks without generating or billing tokens."""

import http.client
import json
import socket
import ssl
from dataclasses import dataclass

from aiwebnovel.ai_writing.provider import MAX_RESPONSE_BYTES, PROVIDER_TIMEOUT_SECONDS
from aiwebnovel.model_gateway.models import ModelProfile
from aiwebnovel.model_gateway.provider import _PublicHTTPSConnection, endpoint_for


@dataclass(frozen=True, slots=True)
class ConnectionResult:
    status: str
    configuration_version: str
    model_available: bool = False


def check_metadata(profile: ModelProfile, key: str | None, version: str) -> ConnectionResult:
    if profile.kind == "cloud" and key is None:
        return ConnectionResult("missing_key", version)
    endpoint = endpoint_for(profile.kind, profile.base_url)
    factory = (
        _PublicHTTPSConnection
        if profile.kind == "cloud"
        else http.client.HTTPSConnection
        if endpoint.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = factory(endpoint.host, endpoint.port, timeout=PROVIDER_TIMEOUT_SECONDS)
    headers = {"Accept": "application/json"}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    try:
        path = endpoint.path.removesuffix("/chat/completions") + "/models"
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        statuses = {401: "unauthorized", 403: "forbidden", 404: "unsupported", 405: "unsupported"}
        if response.status != 200:
            return ConnectionResult(statuses.get(response.status, "unavailable"), version)
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return ConnectionResult("invalid_response", version)
        try:
            data = json.loads(raw)
            models = data["data"]
            if not isinstance(models, list) or any(
                not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in models
            ):
                return ConnectionResult("invalid_response", version)
            available = any(item["id"] == profile.model for item in models)
        except (ValueError, KeyError, TypeError, RecursionError):
            return ConnectionResult("invalid_response", version)
        return ConnectionResult("verified" if available else "model_not_found", version, available)
    except TimeoutError:
        return ConnectionResult("timeout", version)
    except ssl.SSLError:
        return ConnectionResult("certificate_error", version)
    except socket.gaierror:
        return ConnectionResult("dns_error", version)
    except (OSError, http.client.HTTPException):
        return ConnectionResult("unavailable", version)
    finally:
        connection.close()

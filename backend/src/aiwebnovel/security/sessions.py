"""Process-local browser sessions with bounded lifetime and no persistence."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

_HTTP_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


class SessionConfigurationError(ValueError):
    """Raised when a session boundary cannot be configured safely."""


class SessionStatus(StrEnum):
    """Non-secret session lookup outcomes used by CSRF enforcement."""

    ACTIVE = "active"
    MISSING = "missing"
    EXPIRED = "expired"
    CSRF_INVALID = "csrf_invalid"


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """Secrets returned exactly once to the response-building boundary."""

    session_id: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_in_seconds: int


@dataclass(frozen=True, slots=True)
class _SessionRecord:
    csrf_digest: bytes = field(repr=False)
    expires_at: float


class SessionBootstrapResponse(BaseModel):
    """Initial CSRF material for a local, non-authenticating browser session."""

    csrf_token: str = Field(description="Ephemeral in-memory CSRF token for this local session.")
    expires_in_seconds: int = Field(gt=0)


def validate_cookie_name(value: str) -> str:
    """Validate a cookie name as an RFC token without accepting separators."""
    if not isinstance(value, str) or _HTTP_TOKEN.fullmatch(value) is None:
        raise SessionConfigurationError("session cookie name must be a safe HTTP token")
    return value


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


class InMemorySessionManager:
    """Bounded session storage that retains only cryptographic token digests."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or ttl_seconds <= 0:
            raise SessionConfigurationError("session TTL must be a positive integer")
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries <= 0:
            raise SessionConfigurationError("session capacity must be a positive integer")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._records: OrderedDict[bytes, _SessionRecord] = OrderedDict()
        self._lock = threading.Lock()

    def issue(self) -> IssuedSession:
        """Create independent session and CSRF tokens after bounded cleanup."""
        session_id = self._new_unique_session_id()
        csrf_token = self._new_token_distinct_from(session_id)
        now = self._clock()
        session_digest = _digest(session_id)
        with self._lock:
            self._purge_expired(now)
            while len(self._records) >= self.max_entries:
                self._records.popitem(last=False)
            self._records[session_digest] = _SessionRecord(
                csrf_digest=_digest(csrf_token),
                expires_at=now + self.ttl_seconds,
            )
        return IssuedSession(
            session_id=session_id,
            csrf_token=csrf_token,
            expires_in_seconds=self.ttl_seconds,
        )

    def status(self, session_id: str | None) -> SessionStatus:
        """Resolve a session without extending its expiry."""
        if not session_id:
            return SessionStatus.MISSING
        now = self._clock()
        session_digest = _digest(session_id)
        with self._lock:
            record = self._records.get(session_digest)
            if record is None:
                return SessionStatus.MISSING
            if record.expires_at <= now:
                del self._records[session_digest]
                return SessionStatus.EXPIRED
        return SessionStatus.ACTIVE

    def validate_csrf(self, session_id: str | None, csrf_token: str | None) -> SessionStatus:
        """Check session lifetime and CSRF digest using constant-time comparison."""
        if not session_id:
            return SessionStatus.MISSING
        now = self._clock()
        session_digest = _digest(session_id)
        with self._lock:
            record = self._records.get(session_digest)
            if record is None:
                return SessionStatus.MISSING
            if record.expires_at <= now:
                del self._records[session_digest]
                return SessionStatus.EXPIRED
            candidate_digest = _digest(csrf_token or "")
            if not hmac.compare_digest(record.csrf_digest, candidate_digest):
                return SessionStatus.CSRF_INVALID
        return SessionStatus.ACTIVE

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        """Invalidate every process-local session, including during app shutdown."""
        with self._lock:
            self._records.clear()

    def _purge_expired(self, now: float) -> None:
        expired = [digest for digest, record in self._records.items() if record.expires_at <= now]
        for digest in expired:
            del self._records[digest]

    def _new_unique_session_id(self) -> str:
        for _ in range(8):
            candidate = self._token_factory()
            if not candidate:
                continue
            candidate_digest = _digest(candidate)
            with self._lock:
                if candidate_digest not in self._records:
                    return candidate
        raise RuntimeError("secure session token generation failed")

    def _new_token_distinct_from(self, session_id: str) -> str:
        for _ in range(8):
            candidate = self._token_factory()
            if candidate and not hmac.compare_digest(candidate, session_id):
                return candidate
        raise RuntimeError("secure CSRF token generation failed")


def create_security_router(
    manager: InMemorySessionManager,
    *,
    api_prefix: str = "/api/v1",
    cookie_name: str = "aiwebnovel_session",
) -> APIRouter:
    """Build the internal local-session endpoint without adding business writes."""
    validated_cookie_name = validate_cookie_name(cookie_name)
    router = APIRouter(prefix=f"{api_prefix}/security", tags=["security"])

    @router.get(
        "/session",
        response_model=SessionBootstrapResponse,
        summary="Create a temporary local browser session",
        description=(
            "Creates an in-memory CSRF session for the local browser. "
            "This endpoint is not login, identity authentication, or a user account."
        ),
    )
    async def create_local_session(request: Request) -> JSONResponse:
        issued = manager.issue()
        response = JSONResponse(
            content={
                "csrf_token": issued.csrf_token,
                "expires_in_seconds": issued.expires_in_seconds,
            },
            headers={"Cache-Control": "no-store"},
        )
        response.set_cookie(
            validated_cookie_name,
            issued.session_id,
            max_age=issued.expires_in_seconds,
            path="/api",
            secure=request.url.scheme == "https",
            httponly=True,
            samesite="strict",
        )
        return response

    return router

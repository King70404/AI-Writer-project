"""Safe, opt-in delivery of the locally built frontend application."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from fastapi import Request
from fastapi.responses import FileResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from aiwebnovel.core.errors import AppError


FrontendBuildStatus = Literal["ok", "failed"]


@dataclass(frozen=True, slots=True)
class FrontendBuildInspection:
    """Private filesystem inspection result used only inside the backend."""

    status: FrontendBuildStatus
    index_file: Path | None = None


def _project_root() -> Path:
    """Resolve relative build paths against the repository root deterministically."""
    return Path(__file__).resolve().parents[4]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _decode_path_repeatedly(value: str) -> str:
    decoded = value
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def _safe_relative_path(request: Request, route_path: str) -> str | None:
    raw_path = request.scope.get("raw_path", b"")
    if isinstance(raw_path, bytes):
        raw_value = raw_path.decode("ascii", errors="replace")
    else:
        raw_value = str(raw_path)

    candidates = (route_path, raw_value.lstrip("/"))
    for candidate in candidates:
        decoded = _decode_path_repeatedly(candidate)
        if "\x00" in decoded or "\\" in decoded:
            return None
        segments = decoded.split("/")
        if any(
            segment in {".", ".."} or segment.startswith(".")
            for segment in segments
            if segment
        ):
            return None

    normalized = _decode_path_repeatedly(route_path).strip("/")
    return normalized


def _is_api_path(path: str, api_prefix: str) -> bool:
    normalized_path = f"/{path.lstrip('/')}"
    return (
        normalized_path in {"/api", api_prefix}
        or normalized_path.startswith(f"{api_prefix}/")
        or normalized_path.startswith("/api/")
    )


def _is_known_static_request(path: str) -> bool:
    if path == "assets" or path.startswith("assets/"):
        return True
    return bool(Path(path).suffix)


def _accepts_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "").lower()


class FrontendStaticService:
    """Inspect and serve one app instance's configured Vite build."""

    def __init__(self, configured_path: Path, api_prefix: str) -> None:
        self._configured_path = configured_path
        self._api_prefix = api_prefix

    def _root_path(self) -> Path:
        base_path = self._configured_path.expanduser()
        if not base_path.is_absolute():
            base_path = _project_root() / base_path
        return base_path.resolve(strict=False)

    def inspect(self) -> FrontendBuildInspection:
        """Check the required build structure without exposing its location."""
        try:
            root = self._root_path()
            if not root.is_dir():
                return FrontendBuildInspection(status="failed")

            index_file = (root / "index.html").resolve(strict=True)
            assets_directory = (root / "assets").resolve(strict=True)
            if (
                not _is_within(index_file, root)
                or not index_file.is_file()
                or index_file.stat().st_size == 0
                or not _is_within(assets_directory, root)
                or not assets_directory.is_dir()
            ):
                return FrontendBuildInspection(status="failed")
        except OSError:
            return FrontendBuildInspection(status="failed")

        return FrontendBuildInspection(status="ok", index_file=index_file)

    def status(self) -> FrontendBuildStatus:
        """Return only the public readiness status."""
        return self.inspect().status

    def _resolve_file(self, relative_path: str) -> Path | None:
        try:
            root = self._root_path()
            candidate = (root / relative_path).resolve(strict=True)
        except OSError:
            return None
        if not _is_within(candidate, root) or not candidate.is_file():
            return None
        return candidate

    async def serve(self, request: Request, route_path: str) -> Response:
        """Serve a real asset or apply a constrained HTML-only SPA fallback."""
        if _is_api_path(route_path, self._api_prefix):
            raise StarletteHTTPException(status_code=404)

        safe_path = _safe_relative_path(request, route_path)
        if safe_path is None:
            raise StarletteHTTPException(status_code=404)

        inspection = self.inspect()
        if inspection.status != "ok" or inspection.index_file is None:
            raise AppError(
                code="FRONTEND_BUILD_UNAVAILABLE",
                message="前端构建当前不可用，请先完成本地前端构建。",
                status_code=503,
                retryable=True,
                suggested_action="运行前端生产构建后重新检查。",
            )

        if safe_path:
            requested_file = self._resolve_file(safe_path)
            if requested_file is not None:
                return FileResponse(requested_file)

        if _is_known_static_request(safe_path) or not _accepts_html(request):
            raise StarletteHTTPException(status_code=404)

        return FileResponse(inspection.index_file, media_type="text/html")

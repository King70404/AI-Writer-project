"""Read-only storage instance identifier for browser draft isolation."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from aiwebnovel.core.errors import AppError
from aiwebnovel.storage.instance import StorageInstanceService, StorageInstanceUnavailable
from aiwebnovel.storage.paths import StoragePaths


class StorageInstanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    storage_instance_id: str


def _unavailable() -> AppError:
    return AppError(
        code="STORAGE_INSTANCE_UNAVAILABLE",
        message="The storage instance identifier is unavailable.",
        status_code=503,
    )


def create_storage_instance_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix, tags=["Storage"])

    @router.get("/storage-instance", response_model=StorageInstanceResponse)
    def storage_instance(request: Request, response: Response) -> StorageInstanceResponse:
        response.headers["Cache-Control"] = "no-store"
        paths = getattr(request.app.state, "storage_paths", None)
        if not isinstance(paths, StoragePaths) or not getattr(
            request.app.state, "storage_initialized", False
        ):
            raise _unavailable()
        try:
            identifier = StorageInstanceService(paths.root).get()
        except StorageInstanceUnavailable:
            raise _unavailable() from None
        return StorageInstanceResponse(storage_instance_id=identifier)

    return router

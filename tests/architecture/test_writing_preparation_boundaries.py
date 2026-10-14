"""Reference analysis and plans keep model transport and storage behind composition."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "backend/src/aiwebnovel"
MODULES = ("chapter_planning", "writing_studio")


def violations(source: str, layer: str) -> tuple[str, ...]:
    banned = ["alembic", "http", "urllib", "httpx", "requests", "socket", "aiohttp"]
    if layer not in ("composition", "persistence"):
        banned += ["sqlalchemy", "aiwebnovel.db"]
    if layer == "application":
        banned += ["fastapi", "aiwebnovel.model_gateway", "aiwebnovel.core"]
    if layer == "persistence":
        banned += ["fastapi", "aiwebnovel.model_gateway"]
    banned += ["aiwebnovel.ai_writing.provider"]
    allowed_persistence = {
        "composition": {
            "aiwebnovel.chapter_planning.persistence",
            "aiwebnovel.writing_studio.persistence.repository",
        },
        "persistence": {
            "aiwebnovel.novel_structure.persistence.workflow_transaction",
            "aiwebnovel.writing_studio.persistence.models",
        },
    }.get(layer, set())
    imports = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
            if node.level:
                imports.append("relative-import")
    return tuple(
        module
        for module in imports
        if module == "relative-import"
        or any(module == item or module.startswith(item + ".") for item in banned)
        or (
            (".persistence" in module or ".repository" in module)
            and module not in allowed_persistence
        )
        or (layer == "application" and module.endswith((".web", ".composition")))
    )


def test_production_preparation_layers() -> None:
    for module in MODULES:
        for path in (ROOT / module).rglob("*.py"):
            if path.stem == "composition":
                layer = "composition"
            elif path.stem == "web":
                layer = "web"
            elif path.stem == "persistence" or path.parent.name == "persistence":
                layer = "persistence"
            else:
                layer = "application"
            assert violations(path.read_text(encoding="utf-8"), layer) == (), path


@pytest.mark.parametrize(
    "layer,module",
    [
        ("web", "sqlalchemy"),
        ("web", "http.client"),
        ("web", "aiwebnovel.chapter_planning.persistence"),
        ("application", "aiwebnovel.writing_studio.persistence.repository"),
        ("application", "aiwebnovel.writing_studio.composition"),
        ("application", "aiwebnovel.writing_studio.web"),
        ("application", "aiwebnovel.model_gateway.service"),
        ("application", "fastapi"),
        ("persistence", "httpx"),
        ("persistence", "aiwebnovel.model_gateway.service"),
        ("persistence", "aiwebnovel.project.persistence.repository"),
        ("persistence", "aiwebnovel.project.persistence.models"),
        ("composition", "requests"),
    ],
)
def test_preparation_checker_rejects_illegal_import_samples(layer: str, module: str) -> None:
    assert violations(f"import {module}", layer) == (module,)
    assert violations(f"from {module} import Thing", layer) == (module,)


def test_preparation_checker_allows_contracts_and_rejects_relative_bypass() -> None:
    assert not violations("from pydantic import BaseModel", "application")
    assert not violations(
        "from aiwebnovel.character.application.services import CharacterQueryService", "application"
    )
    assert not violations(
        "from aiwebnovel.writing_studio.application.models import WritingRepository", "application"
    )
    assert not violations(
        "from aiwebnovel.chapter_planning.persistence import ChapterPlanningRepository",
        "composition",
    )
    assert violations("from ..persistence import Thing", "application")

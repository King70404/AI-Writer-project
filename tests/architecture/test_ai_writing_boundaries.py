"""AST-enforced AI boundaries with controlled illegal import samples."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "backend/src/aiwebnovel/ai_writing"


def violations(source: str, layer: str) -> tuple[str, ...]:
    banned = ["sqlalchemy", "alembic", "aiwebnovel.db"]
    if layer == "application":
        banned += [
            "fastapi",
            "pydantic",
            "http",
            "urllib",
            "httpx",
            "aiwebnovel.ai_writing.provider",
            "aiwebnovel.ai_writing.web",
            "aiwebnovel.core",
        ]
    elif layer == "web":
        banned += ["http", "urllib", "httpx", "aiwebnovel.ai_writing.provider"]
    elif layer == "provider":
        banned += ["fastapi", "aiwebnovel.ai_writing.web"]
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
            if node.level:
                modules.append("relative-import")
    return tuple(
        m
        for m in modules
        if m == "relative-import"
        or ".persistence" in m
        or ".repository" in m
        or any(m == b or m.startswith(b + ".") for b in banned)
    )


def test_ai_production_boundaries_and_no_fake_implementation() -> None:
    for path in ROOT.rglob("*.py"):
        layer = "application" if path.parent.name == "application" else path.stem
        source = path.read_text(encoding="utf-8")
        assert violations(source, layer) == ()
        assert not any(
            isinstance(n, ast.ClassDef) and n.name.startswith(("Fake", "Mock", "Spy"))
            for n in ast.walk(ast.parse(source))
        )


@pytest.mark.parametrize(
    "layer,module",
    [
        ("application", "fastapi"),
        ("application", "http.client"),
        ("application", "pydantic"),
        ("application", "aiwebnovel.ai_writing.provider"),
        ("web", "sqlalchemy"),
        ("web", "aiwebnovel.ai_writing.provider"),
        ("web", "httpx"),
        ("provider", "fastapi"),
        ("application", "aiwebnovel.project.persistence.repository"),
    ],
)
def test_checker_rejects_controlled_illegal_imports(layer: str, module: str) -> None:
    assert violations(f"import {module}", layer) == (module,)
    assert violations(f"from {module} import Thing", layer) == (module,)


def test_checker_accepts_public_application_contracts_and_rejects_relative_bypass() -> None:
    assert (
        violations(
            "from aiwebnovel.project.application.services import ProjectQueryService", "application"
        )
        == ()
    )
    assert violations("from ..provider import LocalOpenAICompatibleProvider", "application")

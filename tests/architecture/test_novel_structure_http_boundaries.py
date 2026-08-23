"""Controlled AST checks for the novel-structure HTTP adapter boundary."""

import ast
from pathlib import Path

import pytest

WEB_ROOT = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "src"
    / "aiwebnovel"
    / "novel_structure"
    / "web"
)
FORBIDDEN_ROOTS = (
    "sqlalchemy",
    "alembic",
    "aiwebnovel.db",
    "aiwebnovel.novel_structure.persistence",
)


def _forbidden_imports(source: str) -> tuple[str, ...]:
    modules: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return tuple(
        module
        for module in modules
        if any(module == root or module.startswith(f"{root}.") for root in FORBIDDEN_ROOTS)
    )


def test_novel_structure_web_has_no_persistence_or_orm_imports() -> None:
    violations = {
        source.relative_to(WEB_ROOT).as_posix(): _forbidden_imports(
            source.read_text(encoding="utf-8")
        )
        for source in WEB_ROOT.rglob("*.py")
        if _forbidden_imports(source.read_text(encoding="utf-8"))
    }
    assert violations == {}


@pytest.mark.parametrize(
    "source",
    [
        "from sqlalchemy.orm import Session\n",
        "import alembic\n",
        "from aiwebnovel.db.session import create_database_session_factory\n",
        "from aiwebnovel.novel_structure.persistence.repository import Repository\n",
    ],
)
def test_boundary_checker_detects_controlled_illegal_imports(source: str) -> None:
    assert _forbidden_imports(source)


def test_boundary_checker_accepts_http_application_contracts() -> None:
    assert (
        _forbidden_imports(
            "from fastapi import APIRouter\n"
            "from pydantic import BaseModel\n"
            "from aiwebnovel.novel_structure.application.services import "
            "NovelStructureQueryService\n"
        )
        == ()
    )

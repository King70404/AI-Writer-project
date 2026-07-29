"""Controlled positive and negative tests for Character AST boundaries."""

from pathlib import Path

import pytest
from tests.architecture.character_boundaries import check_character_boundaries

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "backend" / "src" / "aiwebnovel"
CANARY = "CHARACTER_SECRET_CANARY"


def _fixture_package(tmp_path: Path) -> Path:
    package_root = tmp_path / "aiwebnovel"
    package_root.mkdir()
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    return package_root


def _write_module(package_root: Path, relative_path: str, source: str) -> None:
    target = package_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def test_current_character_production_boundary_is_clean() -> None:
    assert check_character_boundaries(SOURCE_ROOT) == ()


def test_checker_accepts_declared_character_dependencies(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "character/entities.py",
        "from dataclasses import dataclass\n"
        "from aiwebnovel.domain.revisions import RevisionNumber\n"
        "from aiwebnovel.project.identifiers import ProjectId\n"
        "from .identifiers import CharacterId\n",
    )
    _write_module(package_root, "character/identifiers.py", "VALUE = 1\n")

    assert check_character_boundaries(package_root) == ()


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("from sqlalchemy.orm import Session\n", "character-must-use-declared-dependencies"),
        ("from fastapi import APIRouter\n", "character-must-use-declared-dependencies"),
        ("from pydantic import BaseModel\n", "character-must-use-declared-dependencies"),
        (
            "from aiwebnovel.project.entities import Project\n",
            "character-may-import-only-project-identifiers",
        ),
        (
            "from aiwebnovel.project.repository import ProjectRepository\n",
            "character-may-import-only-project-identifiers",
        ),
        (
            "from aiwebnovel.story_bible import StoryBibleId\n",
            "character-must-not-import-story-bible",
        ),
        ("from aiwebnovel.db.base import Base\n", "character-must-use-declared-dependencies"),
        (
            "from aiwebnovel.core.config import Settings\n",
            "character-must-use-declared-dependencies",
        ),
    ],
)
def test_checker_detects_forbidden_character_imports(
    tmp_path: Path,
    source: str,
    rule: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "character/entities.py", source)

    violations = check_character_boundaries(package_root)

    assert len(violations) == 1
    assert violations[0].rule == rule


@pytest.mark.parametrize("owner", ["project", "story_bible", "domain"])
def test_checker_detects_reverse_dependencies(tmp_path: Path, owner: str) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        f"{owner}/module.py",
        "from aiwebnovel.character import CharacterId\n",
    )

    violations = check_character_boundaries(package_root)

    assert len(violations) == 1
    assert violations[0].rule == "existing-modules-must-not-import-character"


@pytest.mark.parametrize(
    "package_name",
    ["characters", "character_card", "character_cards", "person", "persona", "cast"],
)
def test_checker_detects_forbidden_parallel_package_names(
    tmp_path: Path,
    package_name: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, f"{package_name}/__init__.py", "VALUE = 1\n")

    violations = check_character_boundaries(package_root)

    assert len(violations) == 1
    assert violations[0].rule == "character-package-name-must-be-singular"


def test_violation_render_is_relative_and_does_not_leak_source(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "character/entities.py",
        f"from sqlalchemy import String\nSECRET = {CANARY!r}\n",
    )

    violation = check_character_boundaries(package_root)[0]
    rendered = violation.render(relative_to=package_root)

    assert rendered.startswith("character/entities.py:1:")
    assert CANARY not in rendered

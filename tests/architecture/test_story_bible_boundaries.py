"""Controlled positive and negative tests for Story Bible AST boundaries."""

from pathlib import Path

import pytest
from tests.architecture.story_bible_boundaries import (
    check_story_bible_boundaries,
)

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "backend" / "src" / "aiwebnovel"
CANARY = "STORY_BIBLE_SECRET_CANARY"


def _fixture_package(tmp_path: Path) -> Path:
    package_root = tmp_path / "aiwebnovel"
    package_root.mkdir()
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    return package_root


def _write_module(package_root: Path, relative_path: str, source: str) -> None:
    target = package_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def test_current_story_bible_production_boundary_is_clean() -> None:
    assert check_story_bible_boundaries(SOURCE_ROOT) == ()


def test_checker_accepts_declared_story_bible_dependencies(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "story_bible/entities.py",
        "from dataclasses import dataclass\n"
        "from aiwebnovel.domain.revisions import RevisionNumber\n"
        "from aiwebnovel.project.identifiers import ProjectId\n"
        "from .identifiers import StoryBibleId\n",
    )
    _write_module(package_root, "story_bible/identifiers.py", "VALUE = 1\n")

    assert check_story_bible_boundaries(package_root) == ()


@pytest.mark.parametrize(
    ("module_path", "source", "expected_rule"),
    [
        (
            "story_bible/bad_sqlalchemy.py",
            "import sqlalchemy\n",
            "story-bible-domain-must-not-import-frameworks",
        ),
        (
            "story_bible/bad_fastapi.py",
            "from fastapi import APIRouter\n",
            "story-bible-domain-must-not-import-frameworks",
        ),
        (
            "story_bible/bad_repository.py",
            "from aiwebnovel.project.repository import ProjectRepository\n",
            "story-bible-domain-may-import-only-project-identifiers",
        ),
        (
            "story_bible/bad_entities.py",
            "from aiwebnovel.project.entities import Project\n",
            "story-bible-domain-may-import-only-project-identifiers",
        ),
        (
            "project/bad_reverse.py",
            "from aiwebnovel.story_bible import StoryBible\n",
            "project-must-not-import-story-bible",
        ),
        (
            "domain/bad_reverse.py",
            "from aiwebnovel import story_bible\n",
            "domain-must-not-import-story-bible",
        ),
    ],
)
def test_checker_detects_each_forbidden_dependency(
    tmp_path: Path,
    module_path: str,
    source: str,
    expected_rule: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, module_path, source)

    violations = check_story_bible_boundaries(package_root)

    assert expected_rule in {violation.rule for violation in violations}


@pytest.mark.parametrize(
    "source",
    [
        "from aiwebnovel.db import session\n",
        "from aiwebnovel.core import config\n",
        "from aiwebnovel.security import csrf\n",
        "from aiwebnovel.storage import paths\n",
        "import frontend\n",
        "import pydantic\n",
        "import alembic\n",
    ],
)
def test_checker_rejects_all_other_undeclared_story_bible_dependencies(
    tmp_path: Path,
    source: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "story_bible/bad_dependency.py", source)

    violations = check_story_bible_boundaries(package_root)

    assert violations
    assert all(violation.rule.startswith("story-bible-domain-") for violation in violations)


def test_checker_output_does_not_echo_unrelated_source_content(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "story_bible/bad_canary.py",
        f'SECRET = "{CANARY}"\nimport sqlalchemy\n',
    )

    rendered = "\n".join(
        violation.render(relative_to=package_root)
        for violation in check_story_bible_boundaries(package_root)
    )

    assert "story-bible-domain-must-not-import-frameworks" in rendered
    assert CANARY not in rendered

"""Controlled positive and negative tests for Story Bible AST boundaries."""

import os
import subprocess
import sys
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


def test_checker_accepts_pure_contract_and_declared_persistence_dependencies(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "story_bible/repository.py",
        "from typing import Protocol\n"
        "from aiwebnovel.domain.time import Clock\n"
        "from aiwebnovel.project.identifiers import ProjectId\n"
        "from aiwebnovel.story_bible.entities import StoryBibleAggregate\n",
    )
    _write_module(
        package_root,
        "story_bible/persistence/repository.py",
        "from sqlalchemy.orm import Session\n"
        "from aiwebnovel.db.session import create_database_session_factory\n"
        "from aiwebnovel.project.identifiers import ProjectId\n"
        "from aiwebnovel.project.persistence.models import ProjectRecord\n"
        "from aiwebnovel.story_bible.repository import StoryBibleRepository\n"
        'SQL = "UPDATE story_bibles SET concurrency_version = ? WHERE id = ?"\n',
    )

    assert check_story_bible_boundaries(package_root) == ()


def test_checker_accepts_declared_story_bible_application_dependencies(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "story_bible/application/services.py",
        "from dataclasses import dataclass\n"
        "from aiwebnovel.domain.time import Clock\n"
        "from aiwebnovel.project.identifiers import ProjectId\n"
        "from aiwebnovel.story_bible.entities import StoryBibleAggregate\n"
        "from aiwebnovel.story_bible.repository import StoryBibleRepository\n",
    )

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
            "story_bible/entities.py",
            "from aiwebnovel.story_bible.application.models import StoryBibleSnapshot\n",
            "story-bible-domain-must-not-import-application",
        ),
        (
            "story_bible/repository.py",
            "from aiwebnovel.story_bible.application.services import StoryBibleCommandService\n",
            "story-bible-repository-contract-must-not-import-application",
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


@pytest.mark.parametrize(
    ("module_path", "source", "expected_rule"),
    [
        (
            "story_bible/repository.py",
            "from sqlalchemy.orm import Session\n",
            "story-bible-repository-contract-must-not-import-frameworks",
        ),
        (
            "story_bible/repository.py",
            "from aiwebnovel.story_bible.persistence.repository import Adapter\n",
            "story-bible-repository-contract-must-not-import-adapter",
        ),
        (
            "story_bible/persistence/bad_web.py",
            "from fastapi import APIRouter\n",
            "story-bible-persistence-must-not-import-web-frameworks",
        ),
        (
            "story_bible/persistence/bad_project_service.py",
            "from aiwebnovel.project.application.services import ProjectService\n",
            "story-bible-persistence-must-not-import-project-services",
        ),
    ],
)
def test_checker_separates_contract_and_persistence_boundaries(
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
    ("source", "expected_rule"),
    [
        (
            "import sqlalchemy\n",
            "story-bible-application-must-not-import-frameworks",
        ),
        (
            "from aiwebnovel.story_bible.persistence.repository import "
            "SqlAlchemyStoryBibleRepository\n",
            "story-bible-application-must-not-import-persistence",
        ),
        (
            "from aiwebnovel.story_bible.web import router\n",
            "story-bible-application-must-not-import-web",
        ),
        (
            "from aiwebnovel.db import session\n",
            "story-bible-application-must-use-declared-dependencies",
        ),
        (
            "import frontend\n",
            "story-bible-application-must-use-declared-dependencies",
        ),
    ],
)
def test_checker_rejects_forbidden_application_dependencies(
    tmp_path: Path,
    source: str,
    expected_rule: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "story_bible/application/bad.py", source)

    violations = check_story_bible_boundaries(package_root)

    assert expected_rule in {violation.rule for violation in violations}


def test_checker_keeps_fake_repository_implementations_out_of_production(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "story_bible/application/fakes.py",
        "from aiwebnovel.story_bible.repository import StoryBibleRepository\n"
        "class FakeStoryBibleRepository(StoryBibleRepository):\n"
        "    pass\n",
    )

    violations = check_story_bible_boundaries(package_root)

    assert "story-bible-test-repositories-must-not-enter-production" in {
        violation.rule for violation in violations
    }


def test_checker_rejects_story_table_writes_outside_owned_persistence(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "project/bad_write.py",
        'SQL = "DELETE FROM story_bible_revisions WHERE story_bible_id = ?"\n',
    )

    violations = check_story_bible_boundaries(package_root)

    assert {violation.rule for violation in violations} == {
        "story-bible-tables-written-only-by-story-bible-persistence"
    }


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


def test_application_package_import_has_no_runtime_or_schema_side_effects(
    tmp_path: Path,
) -> None:
    script = (
        "import json, pathlib, sys\n"
        "from aiwebnovel.db.model_registry import load_model_metadata\n"
        "before = sorted(load_model_metadata().tables)\n"
        "before_modules = set(sys.modules)\n"
        "import aiwebnovel.story_bible.application\n"
        "after = sorted(load_model_metadata().tables)\n"
        "forbidden = sorted(name for name in set(sys.modules) - before_modules if "
        "name.startswith(('aiwebnovel.story_bible.persistence', "
        "'aiwebnovel.story_bible.web', 'aiwebnovel.main', 'fastapi')))\n"
        "files = sorted(path.as_posix() for path in pathlib.Path('.').rglob('*') "
        "if path.is_file())\n"
        "print(json.dumps({'before': before, 'after': after, "
        "'forbidden': forbidden, 'files': files}))\n"
    )
    env = os.environ.copy()
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    evidence = completed.stdout.strip()
    expected_tables = (
        '["project_heads", "project_revisions", "projects", '
        '"story_bible_heads", "story_bible_revisions", "story_bibles"]'
    )
    assert f'"before": {expected_tables}' in evidence
    assert f'"after": {expected_tables}' in evidence
    assert '"forbidden": []' in evidence
    assert '"files": []' in evidence

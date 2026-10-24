"""Controlled positive and negative tests for Character AST boundaries."""

import os
import subprocess
import sys
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


def test_checker_accepts_repository_contract_and_persistence_dependencies(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "character/repository.py",
        "from typing import Protocol\n"
        "from aiwebnovel.character.entities import CharacterAggregate\n"
        "from aiwebnovel.domain.time import Clock\n",
    )
    _write_module(
        package_root,
        "character/persistence/repository.py",
        "from sqlalchemy.orm import Session\n"
        "from aiwebnovel.character.repository import CharacterRepository\n"
        "from aiwebnovel.db.session import create_database_session_factory\n"
        "from aiwebnovel.project.persistence.models import ProjectRecord\n",
    )

    assert check_character_boundaries(package_root) == ()


def test_checker_accepts_declared_application_and_list_reader_dependencies(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "character/application/services.py",
        "from aiwebnovel.character.repository import CharacterRepository\n"
        "from aiwebnovel.character.application.list_reader import CharacterListReader\n"
        "from aiwebnovel.domain.time import Clock\n"
        "from aiwebnovel.project.identifiers import ProjectId\n",
    )
    _write_module(
        package_root,
        "character/persistence/list_reader.py",
        "from sqlalchemy.orm import Session\n"
        "from aiwebnovel.character.application.models import CharacterListPage\n"
        "from aiwebnovel.db.session import create_database_session_factory\n"
        "from aiwebnovel.project.persistence.models import ProjectRecord\n",
    )
    _write_module(
        package_root,
        "character/persistence/history_reader.py",
        "from sqlalchemy.orm import Session\n"
        "from aiwebnovel.character.application.history_models import "
        "CharacterRevisionHistoryPage\n"
        "from aiwebnovel.project.persistence.models import ProjectRecord\n",
    )

    assert check_character_boundaries(package_root) == ()


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        (
            "from sqlalchemy.orm import Session\n",
            "character-application-must-use-declared-dependencies",
        ),
        (
            "from fastapi import APIRouter\n",
            "character-application-must-use-declared-dependencies",
        ),
        (
            "from pydantic import BaseModel\n",
            "character-application-must-use-declared-dependencies",
        ),
        (
            "from aiwebnovel.character.persistence.repository import "
            "SqlAlchemyCharacterRepository\n",
            "character-application-must-not-import-persistence",
        ),
        (
            "from aiwebnovel.character.persistence.list_reader import "
            "SqlAlchemyCharacterListReader\n",
            "character-application-must-not-import-persistence",
        ),
        (
            "from aiwebnovel.story_bible import StoryBibleId\n",
            "character-application-must-use-declared-dependencies",
        ),
    ],
)
def test_checker_detects_forbidden_application_imports(
    tmp_path: Path,
    source: str,
    rule: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "character/application/services.py", source)

    violations = check_character_boundaries(package_root)

    assert len(violations) == 1
    assert violations[0].rule == rule


def test_checker_rejects_non_list_adapter_importing_application(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "character/persistence/repository.py",
        "from aiwebnovel.character.application.models import CharacterSnapshot\n",
    )

    violations = check_character_boundaries(package_root)

    assert len(violations) == 1
    assert violations[0].rule == "only-character-read-adapters-may-import-application"


def test_checker_rejects_persistence_list_reader_importing_web(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "character/persistence/list_reader.py",
        "from aiwebnovel.character.web import router\n",
    )

    violations = check_character_boundaries(package_root)

    assert len(violations) == 1
    assert violations[0].rule == "character-persistence-must-not-import-web"


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
        (
            "from aiwebnovel.character.persistence.models import CharacterRecord\n",
            "character-domain-must-not-import-persistence",
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


@pytest.mark.parametrize(
    ("relative_path", "source", "rule"),
    [
        (
            "character/repository.py",
            "from sqlalchemy.orm import Session\n",
            "character-repository-contract-must-be-framework-independent",
        ),
        (
            "character/repository.py",
            "from aiwebnovel.character.persistence.repository import "
            "SqlAlchemyCharacterRepository\n",
            "character-repository-contract-must-be-framework-independent",
        ),
        (
            "character/persistence/repository.py",
            "from fastapi import APIRouter\n",
            "character-persistence-must-use-declared-dependencies",
        ),
        (
            "character/persistence/repository.py",
            "from pydantic import BaseModel\n",
            "character-persistence-must-use-declared-dependencies",
        ),
        (
            "character/persistence/repository.py",
            "from aiwebnovel.project.repository import ProjectRepository\n",
            "character-persistence-may-only-read-project-model",
        ),
        (
            "character/persistence/repository.py",
            "from aiwebnovel.story_bible.persistence.models import StoryBibleRecord\n",
            "character-persistence-must-not-import-story-bible",
        ),
    ],
)
def test_checker_detects_forbidden_repository_and_persistence_imports(
    tmp_path: Path,
    relative_path: str,
    source: str,
    rule: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, relative_path, source)

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


@pytest.mark.parametrize("layer", ["dto.py", "history", "listing"])
def test_checker_detects_unauthorized_later_character_layers(
    tmp_path: Path,
    layer: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    relative_path = f"character/{layer}/__init__.py" if "." not in layer else f"character/{layer}"
    _write_module(package_root, relative_path, "VALUE = 1\n")

    violations = check_character_boundaries(package_root)

    assert len(violations) == 1
    assert violations[0].rule == ("character-persistence-task-must-not-add-later-layers")


def test_character_web_accepts_declared_http_and_application_dependencies(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "character/web/router.py",
        "from fastapi import APIRouter\n"
        "from pydantic import BaseModel\n"
        "from aiwebnovel.api.etags import format_strong_etag\n"
        "from aiwebnovel.character.application.services import CharacterQueryService\n",
    )

    assert check_character_boundaries(package_root) == ()


@pytest.mark.parametrize(
    ("statement", "rule"),
    [
        (
            "from sqlalchemy import select\n",
            "character-web-must-not-import-persistence-frameworks",
        ),
        (
            "from aiwebnovel.character.persistence.repository import "
            "SqlAlchemyCharacterRepository\n",
            "character-web-must-not-import-concrete-adapters",
        ),
        (
            "from aiwebnovel.story_bible.web import router\n",
            "character-web-must-use-declared-dependencies",
        ),
    ],
)
def test_character_web_rejects_undeclared_dependencies(
    tmp_path: Path,
    statement: str,
    rule: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "character/web/router.py", statement)

    violations = check_character_boundaries(package_root)

    assert len(violations) == 1
    assert violations[0].rule == rule


def test_checker_rejects_fake_repository_in_production(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "character/persistence/fakes.py",
        "class FakeCharacterRepository:\n    pass\n",
    )

    violations = check_character_boundaries(package_root)

    assert len(violations) == 1
    assert violations[0].rule == "fake-character-repository-must-remain-in-tests"


def test_application_and_list_reader_imports_have_no_runtime_or_schema_side_effects(
    tmp_path: Path,
) -> None:
    script = (
        "import json, pathlib, sys\n"
        "from aiwebnovel.db.model_registry import load_model_metadata\n"
        "before = sorted(load_model_metadata().tables)\n"
        "before_modules = set(sys.modules)\n"
        "import aiwebnovel.character.application\n"
        "import aiwebnovel.character.persistence.list_reader\n"
        "import aiwebnovel.character.persistence.history_reader\n"
        "after = sorted(load_model_metadata().tables)\n"
        "forbidden = sorted(name for name in set(sys.modules) - before_modules if "
        "name.startswith(('aiwebnovel.character.persistence.repository', "
        "'aiwebnovel.character.web', 'aiwebnovel.main', 'aiwebnovel.storage', "
        "'fastapi')))\n"
        "files = sorted(path.as_posix() for path in pathlib.Path('.').rglob('*') "
        "if path.is_file())\n"
        "print(json.dumps({'before': before, 'after': after, "
        "'forbidden': forbidden, 'files': files}))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=os.environ.copy(),
        check=True,
        capture_output=True,
        text=True,
    )

    evidence = completed.stdout.strip()
    expected_tables = (
        '["ai_candidate_edit_adoptions", "ai_candidate_edits", "ai_workflow_candidates", "ai_workflow_runs", '
        '"chapter_editorial_revisions", "chapter_heads", "chapter_plan_revisions", "chapter_revisions", "chapters", '
        '"character_heads", "character_revisions", "characters", "model_budget_reservations", "model_price_revisions", "model_usage_attempts", '
        '"outline_heads", "outline_revisions", "outlines", '
        '"project_budget_revisions", "project_heads", "project_revisions", "projects", '
        '"story_bible_heads", "story_bible_revisions", "story_bibles", "story_memory_revisions", '
        '"volume_heads", "volume_revisions", "volumes", '
        '"writing_references", "writing_rule_versions"]'
    )
    assert f'"before": {expected_tables}' in evidence
    assert f'"after": {expected_tables}' in evidence
    assert '"forbidden": []' in evidence
    assert '"files": []' in evidence


def test_character_web_import_has_no_runtime_or_schema_side_effects(
    tmp_path: Path,
) -> None:
    script = (
        "import json, pathlib, sys\n"
        "from aiwebnovel.db.model_registry import load_model_metadata\n"
        "before = sorted(load_model_metadata().tables)\n"
        "before_modules = set(sys.modules)\n"
        "import aiwebnovel.character.web\n"
        "after = sorted(load_model_metadata().tables)\n"
        "forbidden = sorted(name for name in set(sys.modules) - before_modules if "
        "name.startswith(('aiwebnovel.character.persistence', 'aiwebnovel.main', "
        "'aiwebnovel.storage', 'sqlalchemy.engine')))\n"
        "files = sorted(path.as_posix() for path in pathlib.Path('.').rglob('*') "
        "if path.is_file())\n"
        "print(json.dumps({'before': before, 'after': after, "
        "'forbidden': forbidden, 'files': files}))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=os.environ.copy(),
        check=True,
        capture_output=True,
        text=True,
    )

    evidence = completed.stdout.strip()
    expected_tables = (
        '["ai_candidate_edit_adoptions", "ai_candidate_edits", "ai_workflow_candidates", "ai_workflow_runs", '
        '"chapter_editorial_revisions", "chapter_heads", "chapter_plan_revisions", "chapter_revisions", "chapters", '
        '"character_heads", "character_revisions", "characters", "model_budget_reservations", "model_price_revisions", "model_usage_attempts", '
        '"outline_heads", "outline_revisions", "outlines", '
        '"project_budget_revisions", "project_heads", "project_revisions", "projects", '
        '"story_bible_heads", "story_bible_revisions", "story_bibles", "story_memory_revisions", '
        '"volume_heads", "volume_revisions", "volumes", '
        '"writing_references", "writing_rule_versions"]'
    )
    assert f'"before": {expected_tables}' in evidence
    assert f'"after": {expected_tables}' in evidence
    assert '"forbidden": []' in evidence
    assert '"files": []' in evidence


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

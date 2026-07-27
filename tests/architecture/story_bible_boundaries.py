"""AST dependency scanner for the pure Story Bible domain boundary."""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_STANDARD_LIBRARY_ROOTS = frozenset({"__future__", *sys.stdlib_module_names})
_FRAMEWORK_ROOTS = frozenset({"alembic", "fastapi", "pydantic", "sqlalchemy"})
_STORY_BIBLE_ROOT = "aiwebnovel.story_bible"
_STORY_BIBLE_APPLICATION = "aiwebnovel.story_bible.application"
_STORY_BIBLE_REPOSITORY = "aiwebnovel.story_bible.repository"
_STORY_BIBLE_PERSISTENCE = "aiwebnovel.story_bible.persistence"
_STORY_BIBLE_WEB = "aiwebnovel.story_bible.web"
_STORY_BIBLE_TABLE_WRITE_PATTERN = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE(?:\s+OR\s+\w+)?"
    r"|DELETE\s+FROM|REPLACE\s+INTO)\s+"
    r"[\"`\[]?(?:story_bibles|story_bible_revisions|story_bible_heads)[\"`\]]?"
    r"(?![A-Z0-9_])",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True, order=True)
class StoryBibleArchitectureViolation:
    """One safe, deterministic Story Bible dependency violation."""

    path: Path
    line: int
    rule: str
    message: str

    def render(self, *, relative_to: Path | None = None) -> str:
        display_path = self.path
        if relative_to is not None and self.path.is_relative_to(relative_to):
            display_path = self.path.relative_to(relative_to)
        return f"{display_path.as_posix()}:{self.line}: [{self.rule}] {self.message}"


@dataclass(frozen=True, slots=True)
class _ImportReference:
    path: Path
    line: int
    source_module: str
    target_module: str


def _module_name(package_root: Path, source_file: Path) -> str:
    relative = source_file.relative_to(package_root)
    parts = [package_root.name, *relative.with_suffix("").parts]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_name(module_name: str, source_file: Path) -> str:
    return module_name if source_file.name == "__init__.py" else module_name.rpartition(".")[0]


def _resolve_from_import(
    node: ast.ImportFrom,
    *,
    package_name: str,
) -> tuple[str, ...]:
    if node.level == 0:
        base_module = node.module or ""
    else:
        package_parts = package_name.split(".") if package_name else []
        retained_parts = len(package_parts) - node.level + 1
        if retained_parts < 1:
            return ()
        resolved_parts = package_parts[:retained_parts]
        if node.module:
            resolved_parts.extend(node.module.split("."))
        base_module = ".".join(resolved_parts)

    targets = [base_module] if base_module else []
    if node.module is None or base_module in {
        "aiwebnovel",
        "aiwebnovel.domain",
        "aiwebnovel.project",
        "aiwebnovel.story_bible",
    }:
        targets.extend(
            f"{base_module}.{alias.name}" if base_module else alias.name
            for alias in node.names
            if alias.name != "*"
        )
    return tuple(targets)


def _import_references(package_root: Path) -> tuple[_ImportReference, ...]:
    references: list[_ImportReference] = []
    for source_file in sorted(package_root.rglob("*.py")):
        module_name = _module_name(package_root, source_file)
        package_name = _package_name(module_name, source_file)
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                targets = _resolve_from_import(node, package_name=package_name)
            else:
                continue
            references.extend(
                _ImportReference(
                    path=source_file,
                    line=node.lineno,
                    source_module=module_name,
                    target_module=target,
                )
                for target in targets
            )
    return tuple(
        sorted(
            references,
            key=lambda item: (
                item.path.as_posix(),
                item.line,
                item.source_module,
                item.target_module,
            ),
        )
    )


def _is_module_or_child(module_name: str, parent: str) -> bool:
    return module_name == parent or module_name.startswith(f"{parent}.")


def _story_bible_domain_violation(
    reference: _ImportReference,
) -> tuple[str, str] | None:
    target = reference.target_module
    target_root = target.partition(".")[0]
    if target_root in _FRAMEWORK_ROOTS:
        return (
            "story-bible-domain-must-not-import-frameworks",
            "Story Bible domain code must remain independent of persistence and web frameworks",
        )
    if target_root in _STANDARD_LIBRARY_ROOTS:
        return None
    if _is_module_or_child(target, _STORY_BIBLE_APPLICATION):
        return (
            "story-bible-domain-must-not-import-application",
            "Story Bible domain code must not depend on its application layer",
        )
    if _is_module_or_child(target, _STORY_BIBLE_PERSISTENCE):
        return (
            "story-bible-domain-must-not-import-persistence",
            "Story Bible domain code must not load its SQLAlchemy persistence adapter",
        )
    if (
        _is_module_or_child(target, _STORY_BIBLE_ROOT)
        or _is_module_or_child(target, "aiwebnovel.domain")
        or target == "aiwebnovel.project.identifiers"
    ):
        return None
    if _is_module_or_child(target, "aiwebnovel.project"):
        return (
            "story-bible-domain-may-import-only-project-identifiers",
            "Story Bible may use only the Project identifier ownership contract",
        )
    return (
        "story-bible-domain-must-use-declared-dependencies",
        "Story Bible domain code may import only the standard library, common domain, and ProjectId",
    )


def _story_bible_repository_violation(
    reference: _ImportReference,
) -> tuple[str, str] | None:
    target = reference.target_module
    target_root = target.partition(".")[0]
    if target_root in _FRAMEWORK_ROOTS:
        return (
            "story-bible-repository-contract-must-not-import-frameworks",
            "The Story Bible repository contract must remain pure Python",
        )
    if target_root in _STANDARD_LIBRARY_ROOTS:
        return None
    if _is_module_or_child(target, _STORY_BIBLE_APPLICATION):
        return (
            "story-bible-repository-contract-must-not-import-application",
            "The Story Bible repository contract must not depend on application use cases",
        )
    if _is_module_or_child(target, _STORY_BIBLE_PERSISTENCE):
        return (
            "story-bible-repository-contract-must-not-import-adapter",
            "The repository contract must not load its SQLAlchemy adapter",
        )
    if (
        _is_module_or_child(target, _STORY_BIBLE_ROOT)
        or _is_module_or_child(target, "aiwebnovel.domain")
        or target == "aiwebnovel.project.identifiers"
    ):
        return None
    return (
        "story-bible-repository-contract-must-use-declared-dependencies",
        "The repository contract may use only Story Bible domain contracts and ProjectId",
    )


def _story_bible_application_violation(
    reference: _ImportReference,
) -> tuple[str, str] | None:
    target = reference.target_module
    target_root = target.partition(".")[0]
    if target_root in _FRAMEWORK_ROOTS:
        return (
            "story-bible-application-must-not-import-frameworks",
            "Story Bible application code must remain independent of persistence and web frameworks",
        )
    if target_root in _STANDARD_LIBRARY_ROOTS:
        return None
    if _is_module_or_child(target, _STORY_BIBLE_PERSISTENCE):
        return (
            "story-bible-application-must-not-import-persistence",
            "Story Bible application services must use only the repository contract",
        )
    if _is_module_or_child(target, _STORY_BIBLE_WEB):
        return (
            "story-bible-application-must-not-import-web",
            "Story Bible application code must not depend on a web adapter",
        )
    if (
        _is_module_or_child(target, _STORY_BIBLE_APPLICATION)
        or _is_module_or_child(target, _STORY_BIBLE_ROOT)
        or _is_module_or_child(target, "aiwebnovel.domain")
        or target == "aiwebnovel.project.identifiers"
    ):
        return None
    return (
        "story-bible-application-must-use-declared-dependencies",
        "Story Bible application code may use only domain contracts, ProjectId, and its repository port",
    )


def _story_bible_persistence_violation(
    reference: _ImportReference,
) -> tuple[str, str] | None:
    target = reference.target_module
    target_root = target.partition(".")[0]
    if target_root in {"fastapi", "pydantic", "alembic"}:
        return (
            "story-bible-persistence-must-not-import-web-frameworks",
            "Story Bible persistence must not import FastAPI, Pydantic, or Alembic",
        )
    if target_root in _STANDARD_LIBRARY_ROOTS or target_root == "sqlalchemy":
        return None
    if (
        _is_module_or_child(target, _STORY_BIBLE_ROOT)
        or _is_module_or_child(target, "aiwebnovel.domain")
        or _is_module_or_child(target, "aiwebnovel.db")
        or target == "aiwebnovel.project.identifiers"
        or target == "aiwebnovel.project.persistence.models"
    ):
        return None
    if _is_module_or_child(target, "aiwebnovel.project"):
        return (
            "story-bible-persistence-must-not-import-project-services",
            "Story Bible persistence may read only Project records and identifiers",
        )
    return (
        "story-bible-persistence-must-use-declared-dependencies",
        "Story Bible persistence may use only SQLAlchemy and declared domain/database contracts",
    )


def _story_bible_web_violation(
    reference: _ImportReference,
) -> tuple[str, str] | None:
    target = reference.target_module
    target_root = target.partition(".")[0]
    if target_root in _STANDARD_LIBRARY_ROOTS or target_root in {"fastapi", "pydantic"}:
        return None
    if target_root in {"sqlalchemy", "alembic"}:
        return (
            "story-bible-web-must-not-import-persistence-frameworks",
            "Story Bible Web must not import SQLAlchemy or Alembic",
        )
    if _is_module_or_child(target, _STORY_BIBLE_PERSISTENCE):
        return (
            "story-bible-web-must-not-import-concrete-repository",
            "Story Bible Web must use composed application services, not persistence adapters",
        )
    if (
        _is_module_or_child(target, _STORY_BIBLE_WEB)
        or _is_module_or_child(target, _STORY_BIBLE_APPLICATION)
        or _is_module_or_child(target, _STORY_BIBLE_ROOT)
        or _is_module_or_child(target, "aiwebnovel.domain")
        or _is_module_or_child(target, "aiwebnovel.api")
        or target == "aiwebnovel.core.errors"
        or target == "aiwebnovel.project.identifiers"
        or target == "aiwebnovel.security.request_limits"
    ):
        return None
    return (
        "story-bible-web-must-use-declared-dependencies",
        "Story Bible Web may use only its application/domain contracts and public HTTP helpers",
    )


def check_story_bible_boundaries(
    package_root: Path,
) -> tuple[StoryBibleArchitectureViolation, ...]:
    """Return all Story Bible and reverse-dependency violations under a package."""
    violations: list[StoryBibleArchitectureViolation] = []
    for reference in _import_references(package_root):
        result: tuple[str, str] | None = None
        if _is_module_or_child(reference.source_module, _STORY_BIBLE_PERSISTENCE):
            result = _story_bible_persistence_violation(reference)
        elif _is_module_or_child(reference.source_module, _STORY_BIBLE_APPLICATION):
            result = _story_bible_application_violation(reference)
        elif _is_module_or_child(reference.source_module, _STORY_BIBLE_WEB):
            result = _story_bible_web_violation(reference)
        elif reference.source_module == _STORY_BIBLE_REPOSITORY:
            result = _story_bible_repository_violation(reference)
        elif _is_module_or_child(reference.source_module, _STORY_BIBLE_ROOT):
            result = _story_bible_domain_violation(reference)
        elif _is_module_or_child(
            reference.source_module, "aiwebnovel.project"
        ) and _is_module_or_child(reference.target_module, _STORY_BIBLE_ROOT):
            result = (
                "project-must-not-import-story-bible",
                "Project must not depend on the Story Bible business module",
            )
        elif _is_module_or_child(
            reference.source_module, "aiwebnovel.domain"
        ) and _is_module_or_child(reference.target_module, "aiwebnovel.story_bible"):
            result = (
                "domain-must-not-import-story-bible",
                "The common domain package must not depend on Story Bible",
            )
        if result is not None:
            rule, message = result
            violations.append(
                StoryBibleArchitectureViolation(
                    path=reference.path,
                    line=reference.line,
                    rule=rule,
                    message=message,
                )
            )
    for source_file in sorted(package_root.rglob("*.py")):
        module_name = _module_name(package_root, source_file)
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        if _is_module_or_child(module_name, _STORY_BIBLE_ROOT):
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                base_names = {base.id for base in node.bases if isinstance(base, ast.Name)} | {
                    base.attr for base in node.bases if isinstance(base, ast.Attribute)
                }
                if (
                    "fake" in node.name.lower() or "spy" in node.name.lower()
                ) and "StoryBibleRepository" in base_names:
                    violations.append(
                        StoryBibleArchitectureViolation(
                            path=source_file,
                            line=node.lineno,
                            rule="story-bible-test-repositories-must-not-enter-production",
                            message=("Fake and spy Story Bible repositories belong only in tests"),
                        )
                    )
        if _is_module_or_child(module_name, _STORY_BIBLE_PERSISTENCE):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _STORY_BIBLE_TABLE_WRITE_PATTERN.search(node.value)
            ):
                violations.append(
                    StoryBibleArchitectureViolation(
                        path=source_file,
                        line=node.lineno,
                        rule="story-bible-tables-written-only-by-story-bible-persistence",
                        message=(
                            "Only Story Bible persistence may issue direct writes to "
                            "Story Bible-owned tables"
                        ),
                    )
                )
    return tuple(sorted(violations))

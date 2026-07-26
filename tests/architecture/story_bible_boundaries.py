"""AST dependency scanner for the pure Story Bible domain boundary."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

_STANDARD_LIBRARY_ROOTS = frozenset({"__future__", *sys.stdlib_module_names})
_FRAMEWORK_ROOTS = frozenset({"alembic", "fastapi", "pydantic", "sqlalchemy"})


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


def _story_bible_violation(
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
    if (
        _is_module_or_child(target, "aiwebnovel.story_bible")
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


def check_story_bible_boundaries(
    package_root: Path,
) -> tuple[StoryBibleArchitectureViolation, ...]:
    """Return all Story Bible and reverse-dependency violations under a package."""
    violations: list[StoryBibleArchitectureViolation] = []
    for reference in _import_references(package_root):
        result: tuple[str, str] | None = None
        if _is_module_or_child(reference.source_module, "aiwebnovel.story_bible"):
            result = _story_bible_violation(reference)
        elif _is_module_or_child(
            reference.source_module, "aiwebnovel.project"
        ) and _is_module_or_child(reference.target_module, "aiwebnovel.story_bible"):
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
    return tuple(sorted(violations))

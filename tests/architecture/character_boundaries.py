"""AST dependency scanner for the pure Character domain boundary."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

_STANDARD_LIBRARY_ROOTS = frozenset({"__future__", *sys.stdlib_module_names})
_CHARACTER_ROOT = "aiwebnovel.character"
_REVERSE_ROOTS = (
    "aiwebnovel.domain",
    "aiwebnovel.project",
    "aiwebnovel.story_bible",
)
_FORBIDDEN_PACKAGE_NAMES = frozenset(
    {"cast", "character_card", "character_cards", "characters", "person", "persona"}
)


@dataclass(frozen=True, slots=True, order=True)
class CharacterArchitectureViolation:
    """One safe, deterministic Character dependency violation."""

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


def _resolve_from_import(node: ast.ImportFrom, package_name: str) -> tuple[str, ...]:
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
        "aiwebnovel.character",
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
                targets = _resolve_from_import(node, package_name)
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


def _character_dependency_violation(
    target: str,
) -> tuple[str, str] | None:
    target_root = target.partition(".")[0]
    if target_root in _STANDARD_LIBRARY_ROOTS:
        return None
    if (
        _is_module_or_child(target, _CHARACTER_ROOT)
        or _is_module_or_child(target, "aiwebnovel.domain")
        or target == "aiwebnovel.project.identifiers"
    ):
        return None
    if _is_module_or_child(target, "aiwebnovel.project"):
        return (
            "character-may-import-only-project-identifiers",
            "Character may use only the Project identifier ownership contract",
        )
    if _is_module_or_child(target, "aiwebnovel.story_bible"):
        return (
            "character-must-not-import-story-bible",
            "Character must remain independent of Story Bible",
        )
    return (
        "character-must-use-declared-dependencies",
        "Character may import only the standard library, common domain, and ProjectId",
    )


def check_character_boundaries(
    package_root: Path,
) -> tuple[CharacterArchitectureViolation, ...]:
    """Return Character dependency, reverse dependency, and naming violations."""
    violations: list[CharacterArchitectureViolation] = []
    for reference in _import_references(package_root):
        result: tuple[str, str] | None = None
        if _is_module_or_child(reference.source_module, _CHARACTER_ROOT):
            result = _character_dependency_violation(reference.target_module)
        elif any(
            _is_module_or_child(reference.source_module, reverse_root)
            for reverse_root in _REVERSE_ROOTS
        ) and _is_module_or_child(reference.target_module, _CHARACTER_ROOT):
            result = (
                "existing-modules-must-not-import-character",
                "Project, Story Bible, and common domain must not depend on Character",
            )
        if result is not None:
            rule, message = result
            violations.append(
                CharacterArchitectureViolation(
                    path=reference.path,
                    line=reference.line,
                    rule=rule,
                    message=message,
                )
            )

    for child in sorted(package_root.iterdir()):
        if child.is_dir() and child.name in _FORBIDDEN_PACKAGE_NAMES:
            violations.append(
                CharacterArchitectureViolation(
                    path=child,
                    line=1,
                    rule="character-package-name-must-be-singular",
                    message="Character production code must use only aiwebnovel.character",
                )
            )
    return tuple(sorted(set(violations)))

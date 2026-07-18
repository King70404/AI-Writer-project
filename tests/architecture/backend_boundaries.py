"""AST-based dependency checks for the current backend infrastructure layers."""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Layer = Literal["core", "storage", "db", "security", "diagnostics", "web", "main"]

_LAYERS: tuple[Layer, ...] = (
    "core",
    "storage",
    "db",
    "security",
    "diagnostics",
    "web",
    "main",
)
_FORBIDDEN_LAYER_IMPORTS: dict[tuple[Layer, Layer], str] = {
    ("core", "storage"): "core-must-not-import-storage",
    ("core", "db"): "core-must-not-import-db",
    ("core", "security"): "core-must-not-import-security",
    ("core", "web"): "core-must-not-import-web",
    ("core", "diagnostics"): "core-must-not-import-diagnostics",
    ("core", "main"): "core-must-not-import-main",
    ("storage", "db"): "storage-must-not-import-db",
    ("storage", "security"): "storage-must-not-import-security",
    ("storage", "web"): "storage-must-not-import-web",
    ("storage", "diagnostics"): "storage-must-not-import-diagnostics",
    ("storage", "main"): "storage-must-not-import-main",
    ("db", "security"): "db-must-not-import-security",
    ("db", "web"): "db-must-not-import-web",
    ("db", "diagnostics"): "db-must-not-import-diagnostics",
    ("db", "main"): "db-must-not-import-main",
    ("security", "storage"): "security-must-not-import-storage",
    ("security", "db"): "security-must-not-import-db",
    ("security", "web"): "security-must-not-import-web",
    ("security", "diagnostics"): "security-must-not-import-diagnostics",
    ("security", "main"): "security-must-not-import-main",
    ("web", "storage"): "web-must-not-import-storage",
    ("web", "db"): "web-must-not-import-db",
    ("web", "diagnostics"): "web-must-not-import-diagnostics",
    ("web", "main"): "web-must-not-import-main",
    ("diagnostics", "web"): "diagnostics-must-not-import-web",
    ("diagnostics", "main"): "diagnostics-must-not-import-main",
    ("main", "diagnostics"): "main-must-not-import-diagnostics",
}
_PUBLIC_STORAGE_MODULES_FOR_DB = {
    "aiwebnovel.storage.paths",
}
_PUBLIC_SECURITY_MODULES_FOR_WEB = {
    "aiwebnovel.security.dto",
    "aiwebnovel.security.responses",
}
_PUBLIC_MODULES_FOR_DIAGNOSTICS: dict[Layer, frozenset[str]] = {
    "core": frozenset({"aiwebnovel.core.config"}),
    "storage": frozenset({"aiwebnovel.storage"}),
    "db": frozenset({"aiwebnovel.db"}),
    "security": frozenset({"aiwebnovel.security"}),
}
_DIAGNOSTICS_PUBLIC_CONTRACT_RULES: dict[Layer, str] = {
    "core": "diagnostics-must-use-public-core-config-contract",
    "storage": "diagnostics-must-use-public-storage-contract",
    "db": "diagnostics-must-use-public-db-contract",
    "security": "diagnostics-must-use-public-security-contract",
}
_SESSION_PERSISTENCE_MODULES = {
    "dbm",
    "pathlib",
    "shelve",
    "sqlite3",
    "sqlalchemy",
}
_LOCAL_APP_DATA_OWNER = "aiwebnovel.core.config"


@dataclass(frozen=True, slots=True, order=True)
class ArchitectureViolation:
    """One deterministic source location that violates a backend boundary."""

    path: Path
    line: int
    rule: str
    message: str

    def render(self, *, relative_to: Path | None = None) -> str:
        """Render a concise diagnostic without hiding the offending boundary."""
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
    module_parts = [package_root.name, *relative.with_suffix("").parts]
    if module_parts[-1] == "__init__":
        module_parts.pop()
    return ".".join(module_parts)


def _package_name(module_name: str, source_file: Path) -> str:
    if source_file.name == "__init__.py":
        return module_name
    return module_name.rpartition(".")[0]


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
    if base_module in {"aiwebnovel", "tests"}:
        targets.extend(f"{base_module}.{alias.name}" for alias in node.names if alias.name != "*")
    return tuple(targets)


def _import_references(package_root: Path) -> tuple[_ImportReference, ...]:
    references: list[_ImportReference] = []
    for source_file in sorted(package_root.rglob("*.py")):
        module_name = _module_name(package_root, source_file)
        package_name = _package_name(module_name, source_file)
        source_text = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(source_file))

        for node in ast.walk(tree):
            targets: tuple[str, ...]
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


def _layer_for(module_name: str) -> Layer | None:
    if module_name == "aiwebnovel.main":
        return "main"
    for layer in ("core", "storage", "db", "security", "diagnostics", "web"):
        prefix = f"aiwebnovel.{layer}"
        if module_name == prefix or module_name.startswith(f"{prefix}."):
            return layer
    return None


def _imports_tests(module_name: str) -> bool:
    return (
        module_name == "tests"
        or module_name.startswith("tests.")
        or module_name == "aiwebnovel.tests"
        or module_name.startswith("aiwebnovel.tests.")
    )


def _strongly_connected_components(
    graph: dict[Layer, set[Layer]],
) -> tuple[tuple[Layer, ...], ...]:
    next_index = 0
    indices: dict[Layer, int] = {}
    low_links: dict[Layer, int] = {}
    stack: list[Layer] = []
    on_stack: set[Layer] = set()
    components: list[tuple[Layer, ...]] = []

    def visit(node: Layer) -> None:
        nonlocal next_index
        indices[node] = next_index
        low_links[node] = next_index
        next_index += 1
        stack.append(node)
        on_stack.add(node)

        for target in sorted(graph[node]):
            if target not in indices:
                visit(target)
                low_links[node] = min(low_links[node], low_links[target])
            elif target in on_stack:
                low_links[node] = min(low_links[node], indices[target])

        if low_links[node] != indices[node]:
            return

        component: list[Layer] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(tuple(sorted(component)))

    for layer in _LAYERS:
        if layer not in indices:
            visit(layer)
    return tuple(sorted(components))


def check_backend_boundaries(package_root: Path) -> tuple[ArchitectureViolation, ...]:
    """Return every forbidden import and circular layer dependency under a package."""
    resolved_root = package_root.resolve(strict=True)
    references = _import_references(resolved_root)
    violations: list[ArchitectureViolation] = []
    graph: dict[Layer, set[Layer]] = {layer: set() for layer in _LAYERS}
    edge_locations: dict[tuple[Layer, Layer], list[_ImportReference]] = defaultdict(list)

    for reference in references:
        source_layer = _layer_for(reference.source_module)
        target_layer = _layer_for(reference.target_module)

        if source_layer == "diagnostics" and target_layer in _PUBLIC_MODULES_FOR_DIAGNOSTICS:
            allowed_modules = _PUBLIC_MODULES_FOR_DIAGNOSTICS[target_layer]
            if reference.target_module not in allowed_modules:
                violations.append(
                    ArchitectureViolation(
                        path=reference.path,
                        line=reference.line,
                        rule=_DIAGNOSTICS_PUBLIC_CONTRACT_RULES[target_layer],
                        message=(
                            "diagnostics may import only the public "
                            f"{target_layer} diagnostic contract, not "
                            f"{reference.target_module!r}"
                        ),
                    )
                )

        if source_layer == "diagnostics" and (
            reference.target_module == "sqlalchemy"
            or reference.target_module.startswith("sqlalchemy.")
        ):
            violations.append(
                ArchitectureViolation(
                    path=reference.path,
                    line=reference.line,
                    rule="diagnostics-must-not-import-sqlalchemy",
                    message="diagnostics must use the public database diagnostic contract",
                )
            )

        if _imports_tests(reference.target_module):
            violations.append(
                ArchitectureViolation(
                    path=reference.path,
                    line=reference.line,
                    rule="production-must-not-import-tests",
                    message=(
                        f"production module {reference.source_module!r} imports "
                        f"test module {reference.target_module!r}"
                    ),
                )
            )

        if reference.source_module.startswith("aiwebnovel.security.sessions") and any(
            reference.target_module == module or reference.target_module.startswith(f"{module}.")
            for module in _SESSION_PERSISTENCE_MODULES
        ):
            violations.append(
                ArchitectureViolation(
                    path=reference.path,
                    line=reference.line,
                    rule="session-manager-must-remain-in-memory",
                    message="session management must not import file or database persistence",
                )
            )

        if reference.source_module.startswith("aiwebnovel.diagnostics") and (
            reference.target_module == "aiwebnovel.security.sessions"
            or reference.target_module.startswith("aiwebnovel.security.sessions.")
        ):
            violations.append(
                ArchitectureViolation(
                    path=reference.path,
                    line=reference.line,
                    rule="diagnostics-must-not-access-session-internals",
                    message="diagnostics may use only public security diagnostic contracts",
                )
            )

        if source_layer is None or target_layer is None or source_layer == target_layer:
            continue

        graph[source_layer].add(target_layer)
        edge_locations[(source_layer, target_layer)].append(reference)
        if (
            source_layer == "db"
            and target_layer == "storage"
            and reference.target_module not in _PUBLIC_STORAGE_MODULES_FOR_DB
        ):
            violations.append(
                ArchitectureViolation(
                    path=reference.path,
                    line=reference.line,
                    rule="db-must-use-public-storage-paths",
                    message=(
                        "db layer may import only the public StoragePaths contract, not "
                        f"{reference.target_module!r}"
                    ),
                )
            )
        if (
            source_layer == "web"
            and target_layer == "security"
            and reference.target_module not in _PUBLIC_SECURITY_MODULES_FOR_WEB
        ):
            violations.append(
                ArchitectureViolation(
                    path=reference.path,
                    line=reference.line,
                    rule="web-must-use-public-security-contracts",
                    message=(
                        "web layer may import only public security DTO or response "
                        f"contracts, not {reference.target_module!r}"
                    ),
                )
            )
        rule = _FORBIDDEN_LAYER_IMPORTS.get((source_layer, target_layer))
        if rule is not None:
            violations.append(
                ArchitectureViolation(
                    path=reference.path,
                    line=reference.line,
                    rule=rule,
                    message=(
                        f"{source_layer} layer imports forbidden {target_layer} layer "
                        f"through {reference.target_module!r}"
                    ),
                )
            )

    for source_file in sorted(resolved_root.rglob("*.py")):
        module_name = _module_name(resolved_root, source_file)
        if module_name == _LOCAL_APP_DATA_OWNER:
            continue
        source_text = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(source_file))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.strip().upper() == "LOCALAPPDATA"
            ):
                violations.append(
                    ArchitectureViolation(
                        path=source_file,
                        line=node.lineno,
                        rule="localappdata-resolution-owned-by-core-config",
                        message=(
                            "only aiwebnovel.core.config may resolve the LocalAppData "
                            "environment boundary"
                        ),
                    )
                )

            if (
                isinstance(node, ast.BinOp)
                and isinstance(node.op, ast.Div)
                and isinstance(node.right, ast.Constant)
                and node.right.value == "AIWebNovel"
            ):
                violations.append(
                    ArchitectureViolation(
                        path=source_file,
                        line=node.lineno,
                        rule="formal-data-root-owned-by-core-config",
                        message=("only aiwebnovel.core.config may derive the formal data root"),
                    )
                )

        if module_name.startswith("aiwebnovel.security.sessions"):
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                called_name: str | None = None
                if isinstance(node.func, ast.Name):
                    called_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    called_name = node.func.attr
                if called_name in {
                    "open",
                    "touch",
                    "write_bytes",
                    "write_text",
                }:
                    violations.append(
                        ArchitectureViolation(
                            path=source_file,
                            line=node.lineno,
                            rule="session-manager-must-remain-in-memory",
                            message="session management must not perform file persistence",
                        )
                    )

    for component in _strongly_connected_components(graph):
        if len(component) < 2:
            continue
        component_set = set(component)
        cycle_edges = sorted(
            (
                (source, target)
                for source in component
                for target in graph[source]
                if target in component_set
            ),
        )
        first_edge = cycle_edges[0]
        location = edge_locations[first_edge][0]
        violations.append(
            ArchitectureViolation(
                path=location.path,
                line=location.line,
                rule="no-circular-layer-dependencies",
                message=f"circular layer dependency includes {', '.join(component)}",
            )
        )

    return tuple(sorted(set(violations)))

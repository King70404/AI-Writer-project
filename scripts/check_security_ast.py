"""Verify security-critical Python wiring from the repository's real syntax trees."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

_MAIN_PATH = "backend/src/aiwebnovel/main.py"
_CONFIG_PATH = "backend/src/aiwebnovel/core/config.py"
_CSRF_PATH = "backend/src/aiwebnovel/security/csrf.py"
_ENTRYPOINT_PATH = "backend/src/aiwebnovel/__main__.py"
_CHECKER_PATH = "scripts/check_security_ast.py"

_TARGET_PATHS = (_MAIN_PATH, _CONFIG_PATH, _CSRF_PATH, _ENTRYPOINT_PATH)
_SECURITY_FIELDS = (
    "trusted_hosts",
    "max_request_body_bytes",
    "session_cookie_name",
    "session_ttl_seconds",
    "session_max_entries",
    "csrf_header_name",
    "expose_api_docs",
)
_SECURITY_MIDDLEWARE = frozenset(
    {
        "HostValidationMiddleware",
        "RequestLimitsMiddleware",
        "CSRFMiddleware",
        "SecurityHeadersMiddleware",
    }
)
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

Violation = tuple[str, str]


def _load_trees(repository_root: Path) -> tuple[dict[str, ast.Module], list[Violation]]:
    trees: dict[str, ast.Module] = {}
    violations: list[Violation] = []
    for relative_path in _TARGET_PATHS:
        target = repository_root / relative_path
        try:
            source = target.read_text(encoding="utf-8")
            trees[relative_path] = ast.parse(source, filename=relative_path)
        except (OSError, UnicodeError, SyntaxError):
            violations.append(("python-ast-parse-failed", relative_path))
    return trees, violations


def _function_named(
    body: Iterable[ast.stmt], name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for statement in body:
        if (
            isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
            and statement.name == name
        ):
            return statement
    return None


def _class_named(body: Iterable[ast.stmt], name: str) -> ast.ClassDef | None:
    for statement in body:
        if isinstance(statement, ast.ClassDef) and statement.name == name:
            return statement
    return None


def _walk_runtime(node: ast.AST) -> Iterator[ast.AST]:
    """Walk one runtime body without treating nested definitions as active wiring."""
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield from _walk_runtime(child)


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _dotted_name(node.value)
        return f"{owner}.{node.attr}" if owner is not None else node.attr
    return None


def _is_call(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Call) and _dotted_name(node.func) == name


def _is_name(node: ast.AST, name: str) -> bool:
    dotted = _dotted_name(node)
    return dotted == name or (dotted is not None and dotted.endswith(f".{name}"))


def _contains_name(node: ast.AST, name: str) -> bool:
    return any(
        (isinstance(child, ast.Name) and child.id == name)
        or (isinstance(child, ast.Attribute) and child.attr == name)
        for child in ast.walk(node)
    )


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _is_constant(node: ast.AST | None, value: object) -> bool:
    return isinstance(node, ast.Constant) and node.value == value


def _assignment_value(statement: ast.stmt, dotted_target: str) -> ast.expr | None:
    if isinstance(statement, ast.Assign):
        if any(_dotted_name(target) == dotted_target for target in statement.targets):
            return statement.value
    elif isinstance(statement, ast.AnnAssign) and _dotted_name(statement.target) == dotted_target:
        return statement.value
    return None


def _check_main(tree: ast.Module) -> list[Violation]:
    violations: list[Violation] = []
    create_app = _function_named(tree.body, "create_app")
    if create_app is None:
        return [("main-create-app-missing", _MAIN_PATH)]

    runtime_nodes = tuple(_walk_runtime(create_app))
    middleware_calls: dict[str, list[ast.Call]] = {
        middleware: [] for middleware in _SECURITY_MIDDLEWARE
    }
    for node in runtime_nodes:
        if not _is_call(node, "application.add_middleware") or not isinstance(node, ast.Call):
            continue
        if not node.args:
            continue
        for middleware_name in middleware_calls:
            if _is_name(node.args[0], middleware_name):
                middleware_calls[middleware_name].append(node)

    if any(not middleware_calls[middleware_name] for middleware_name in _SECURITY_MIDDLEWARE):
        violations.append(("security-middleware-not-registered", _MAIN_PATH))

    csrf_session_path_is_dynamic = any(
        (session_path := _keyword(call, "session_path")) is not None
        and _contains_name(session_path, "api_prefix")
        for call in middleware_calls["CSRFMiddleware"]
    )
    if not csrf_session_path_is_dynamic:
        violations.append(("main-csrf-session-path-not-dynamic", _MAIN_PATH))

    security_router_is_included = any(
        _is_call(node, "application.include_router")
        and isinstance(node, ast.Call)
        and any(
            isinstance(descendant, ast.Call) and _is_name(descendant.func, "create_security_router")
            for argument in (*node.args, *(keyword.value for keyword in node.keywords))
            for descendant in ast.walk(argument)
        )
        for node in runtime_nodes
    )
    if not security_router_is_included:
        violations.append(("main-security-router-not-included", _MAIN_PATH))

    proxy_headers_disabled = any(
        _is_constant(
            _assignment_value(node, "application.state.proxy_headers_trusted")
            if isinstance(node, ast.stmt)
            else None,
            False,
        )
        for node in runtime_nodes
    )
    if not proxy_headers_disabled:
        violations.append(("main-proxy-headers-state-not-false", _MAIN_PATH))

    fastapi_docs_are_safe = False
    for node in runtime_nodes:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = _assignment_value(node, "application")
        if not isinstance(value, ast.Call) or not _is_name(value.func, "FastAPI"):
            continue
        fastapi_docs_are_safe = (
            _is_constant(_keyword(value, "docs_url"), None)
            and _is_constant(_keyword(value, "redoc_url"), None)
            and (openapi_url := _keyword(value, "openapi_url")) is not None
            and _contains_name(openapi_url, "expose_api_docs")
        )
        if fastapi_docs_are_safe:
            break
    if not fastapi_docs_are_safe:
        violations.append(("main-fastapi-docs-policy-missing", _MAIN_PATH))
    return violations


def _class_field_names(class_node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for statement in class_node.body:
        if isinstance(statement, ast.Assign):
            names.update(target.id for target in statement.targets if isinstance(target, ast.Name))
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            names.add(statement.target.id)
    return names


def _environment_values(method: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    values: set[str] = set()
    for node in _walk_runtime(method):
        if not isinstance(node, ast.Compare) or not node.ops or not node.comparators:
            continue
        if _contains_name(node.left, "environment"):
            if isinstance(node.ops[0], ast.In):
                values.update(
                    child.value
                    for child in ast.walk(node.comparators[0])
                    if isinstance(child, ast.Constant) and isinstance(child.value, str)
                )
            elif isinstance(node.ops[0], ast.Eq) and _is_constant(
                node.comparators[0], "development"
            ):
                values.add("development")
            elif isinstance(node.ops[0], ast.Eq) and _is_constant(node.comparators[0], "test"):
                values.add("test")
        elif _contains_name(node.comparators[0], "environment") and isinstance(node.ops[0], ast.Eq):
            if _is_constant(node.left, "development"):
                values.add("development")
            elif _is_constant(node.left, "test"):
                values.add("test")
    return values


def _check_config(tree: ast.Module) -> list[Violation]:
    settings = _class_named(tree.body, "Settings")
    if settings is None:
        return [("config-settings-class-missing", _CONFIG_PATH)]

    violations = [
        (f"config-field-{field_name.replace('_', '-')}-missing", _CONFIG_PATH)
        for field_name in _SECURITY_FIELDS
        if field_name not in _class_field_names(settings)
    ]
    environment_defaults = _function_named(
        settings.body,
        "apply_environment_security_defaults",
    )
    if environment_defaults is None or not {"development", "test"}.issubset(
        _environment_values(environment_defaults)
    ):
        violations.append(("production-api-docs-default-not-enforced", _CONFIG_PATH))
    return violations


def _string_constants(node: ast.AST) -> set[str]:
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def _check_csrf(tree: ast.Module) -> list[Violation]:
    violations: list[Violation] = []
    unsafe_assignment: ast.expr | None = None
    for statement in tree.body:
        unsafe_assignment = _assignment_value(statement, "UNSAFE_METHODS")
        if unsafe_assignment is not None:
            break
    if unsafe_assignment is None or not _UNSAFE_METHODS.issubset(
        _string_constants(unsafe_assignment)
    ):
        violations.append(("csrf-unsafe-methods-missing", _CSRF_PATH))
    if _class_named(tree.body, "CSRFMiddleware") is None:
        violations.append(("csrf-middleware-class-missing", _CSRF_PATH))
    return violations


def _check_entrypoint(tree: ast.Module) -> list[Violation]:
    main_function = _function_named(tree.body, "main")
    if main_function is None:
        return [("entrypoint-main-function-missing", _ENTRYPOINT_PATH)]

    runtime_nodes = tuple(_walk_runtime(main_function))
    loopback_calls = [
        node
        for node in runtime_nodes
        if isinstance(node, ast.Call) and _is_name(node.func, "validate_loopback_bind_host")
    ]
    uvicorn_calls = [
        node
        for node in runtime_nodes
        if isinstance(node, ast.Call) and _is_call(node, "uvicorn.run")
    ]
    violations: list[Violation] = []
    if (
        not loopback_calls
        or not uvicorn_calls
        or min(call.lineno for call in loopback_calls) >= min(call.lineno for call in uvicorn_calls)
    ):
        violations.append(("entrypoint-loopback-validation-order-invalid", _ENTRYPOINT_PATH))

    uvicorn_is_safe = bool(uvicorn_calls) and all(
        _is_constant(_keyword(call, "proxy_headers"), False)
        and _is_constant(_keyword(call, "server_header"), False)
        and _is_constant(_keyword(call, "forwarded_allow_ips"), "")
        for call in uvicorn_calls
    )
    if not uvicorn_is_safe:
        violations.append(("uvicorn-security-options-not-enforced", _ENTRYPOINT_PATH))
    return violations


def _run(repository_root: Path) -> int:
    trees, violations = _load_trees(repository_root)
    if _MAIN_PATH in trees:
        violations.extend(_check_main(trees[_MAIN_PATH]))
    if _CONFIG_PATH in trees:
        violations.extend(_check_config(trees[_CONFIG_PATH]))
    if _CSRF_PATH in trees:
        violations.extend(_check_csrf(trees[_CSRF_PATH]))
    if _ENTRYPOINT_PATH in trees:
        violations.extend(_check_entrypoint(trees[_ENTRYPOINT_PATH]))

    for rule, relative_path in sorted(set(violations)):
        print(f"{rule}\t{relative_path}")
    return 1 if violations else 0


def _validated_repository_root(argument: str) -> Path | None:
    try:
        repository_root = Path(argument).resolve(strict=True)
        checker_path = Path(__file__).resolve(strict=True)
        expected_checker_path = (repository_root / _CHECKER_PATH).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    if not repository_root.is_dir() or checker_path != expected_checker_path:
        return None
    return repository_root


def main() -> int:
    """Run without ever exposing parser diagnostics or source values."""
    if len(sys.argv) != 2:
        print(f"repository-root-invalid\t{_CHECKER_PATH}")
        return 1
    repository_root = _validated_repository_root(sys.argv[1])
    if repository_root is None:
        print(f"repository-root-invalid\t{_CHECKER_PATH}")
        return 1
    try:
        return _run(repository_root)
    except Exception:  # noqa: BLE001 - the checker must fail closed without leaking details.
        print(f"python-ast-checker-failed\t{_CHECKER_PATH}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

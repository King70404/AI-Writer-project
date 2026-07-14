"""Positive and negative tests for deterministic backend dependency boundaries."""

from pathlib import Path

import pytest

from .backend_boundaries import check_backend_boundaries

pytestmark = pytest.mark.architecture

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_PACKAGE_ROOT = _REPOSITORY_ROOT / "backend" / "src" / "aiwebnovel"


def _write_module(package_root: Path, relative_path: str, source: str) -> None:
    target = package_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def _fixture_package(tmp_path: Path) -> Path:
    package_root = tmp_path / "aiwebnovel"
    _write_module(package_root, "__init__.py", "")
    for layer in ("core", "db", "web"):
        _write_module(package_root, f"{layer}/__init__.py", "")
    return package_root


def test_current_backend_respects_declared_layer_boundaries() -> None:
    violations = check_backend_boundaries(_BACKEND_PACKAGE_ROOT)

    assert not violations, "\n".join(
        violation.render(relative_to=_REPOSITORY_ROOT) for violation in violations
    )


@pytest.mark.parametrize(
    ("module_path", "source", "expected_rule"),
    [
        (
            "core/bad.py",
            "from aiwebnovel.db import session\n",
            "core-must-not-import-db",
        ),
        (
            "core/bad_web.py",
            "from aiwebnovel.web import frontend\n",
            "core-must-not-import-web",
        ),
        (
            "db/bad.py",
            "import aiwebnovel.web.frontend\n",
            "db-must-not-import-web",
        ),
        (
            "web/bad.py",
            "from aiwebnovel.db import session\n",
            "web-must-not-import-db",
        ),
        (
            "core/test_leak.py",
            "from tests.backend import helpers\n",
            "production-must-not-import-tests",
        ),
    ],
    ids=(
        "core-to-db",
        "core-to-web",
        "db-to-web",
        "web-to-db",
        "production-to-tests",
    ),
)
def test_checker_rejects_forbidden_absolute_imports(
    tmp_path: Path,
    module_path: str,
    source: str,
    expected_rule: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, module_path, source)

    violations = check_backend_boundaries(package_root)

    assert expected_rule in {violation.rule for violation in violations}
    rendered = "\n".join(violation.render(relative_to=tmp_path) for violation in violations)
    assert module_path in rendered
    assert expected_rule in rendered


def test_checker_resolves_relative_imports_before_applying_boundaries(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "core/bad_relative.py", "from ..db import session\n")

    violations = check_backend_boundaries(package_root)

    assert "core-must-not-import-db" in {violation.rule for violation in violations}


def test_checker_accepts_composition_root_and_inward_dependencies(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "core/config.py", "VALUE = 1\n")
    _write_module(
        package_root,
        "db/repository.py",
        "from aiwebnovel.core import config\n",
    )
    _write_module(
        package_root,
        "web/frontend.py",
        "from aiwebnovel.core import config\n",
    )
    _write_module(
        package_root,
        "main.py",
        "from aiwebnovel.core import config\n"
        "from aiwebnovel.db import repository\n"
        "from aiwebnovel.web import frontend\n",
    )

    assert check_backend_boundaries(package_root) == ()


def test_checker_reports_circular_layer_dependencies(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "core/uses_main.py", "from aiwebnovel import main\n")
    _write_module(package_root, "main.py", "from aiwebnovel.core import uses_main\n")

    violations = check_backend_boundaries(package_root)

    assert "no-circular-layer-dependencies" in {violation.rule for violation in violations}

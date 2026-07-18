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
    for layer in ("domain", "core", "storage", "db", "security", "diagnostics", "web"):
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
            "core/bad_domain.py",
            "from aiwebnovel.domain import identifiers\n",
            "core-must-not-import-domain",
        ),
        (
            "core/bad_storage.py",
            "from aiwebnovel.storage import paths\n",
            "core-must-not-import-storage",
        ),
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
            "core/bad_security.py",
            "from aiwebnovel.security import health\n",
            "core-must-not-import-security",
        ),
        (
            "core/bad_diagnostics.py",
            "from aiwebnovel import diagnostics\n",
            "core-must-not-import-diagnostics",
        ),
        (
            "storage/bad_db.py",
            "from aiwebnovel.db import session\n",
            "storage-must-not-import-db",
        ),
        (
            "storage/bad_web.py",
            "from aiwebnovel.web import frontend\n",
            "storage-must-not-import-web",
        ),
        (
            "storage/bad_security.py",
            "from aiwebnovel.security import sessions\n",
            "storage-must-not-import-security",
        ),
        (
            "storage/bad_diagnostics.py",
            "from aiwebnovel import diagnostics\n",
            "storage-must-not-import-diagnostics",
        ),
        (
            "db/bad.py",
            "import aiwebnovel.web.frontend\n",
            "db-must-not-import-web",
        ),
        (
            "db/bad_security.py",
            "from aiwebnovel.security import csrf\n",
            "db-must-not-import-security",
        ),
        (
            "db/bad_diagnostics.py",
            "from aiwebnovel import diagnostics\n",
            "db-must-not-import-diagnostics",
        ),
        (
            "security/bad_storage.py",
            "from aiwebnovel.storage import paths\n",
            "security-must-not-import-storage",
        ),
        (
            "security/bad_db.py",
            "from aiwebnovel.db import session\n",
            "security-must-not-import-db",
        ),
        (
            "security/bad_web.py",
            "from aiwebnovel.web import frontend\n",
            "security-must-not-import-web",
        ),
        (
            "security/bad_diagnostics.py",
            "from aiwebnovel import diagnostics\n",
            "security-must-not-import-diagnostics",
        ),
        (
            "web/bad_storage.py",
            "from aiwebnovel.storage import access\n",
            "web-must-not-import-storage",
        ),
        (
            "web/bad.py",
            "from aiwebnovel.db import session\n",
            "web-must-not-import-db",
        ),
        (
            "web/bad_diagnostics.py",
            "from aiwebnovel import diagnostics\n",
            "web-must-not-import-diagnostics",
        ),
        (
            "diagnostics/bad_web.py",
            "from aiwebnovel.web import frontend\n",
            "diagnostics-must-not-import-web",
        ),
        (
            "diagnostics/bad_main.py",
            "from aiwebnovel import main\n",
            "diagnostics-must-not-import-main",
        ),
        (
            "main.py",
            "from aiwebnovel import diagnostics\n",
            "main-must-not-import-diagnostics",
        ),
        (
            "storage/bad_main.py",
            "from aiwebnovel import main\n",
            "storage-must-not-import-main",
        ),
        (
            "security/bad_main.py",
            "from aiwebnovel import main\n",
            "security-must-not-import-main",
        ),
        (
            "core/test_leak.py",
            "from tests.backend import helpers\n",
            "production-must-not-import-tests",
        ),
    ],
    ids=(
        "core-to-domain",
        "core-to-storage",
        "core-to-db",
        "core-to-web",
        "core-to-security",
        "core-to-diagnostics",
        "storage-to-db",
        "storage-to-web",
        "storage-to-security",
        "storage-to-diagnostics",
        "db-to-web",
        "db-to-security",
        "db-to-diagnostics",
        "security-to-storage",
        "security-to-db",
        "security-to-web",
        "security-to-diagnostics",
        "web-to-storage",
        "web-to-db",
        "web-to-diagnostics",
        "diagnostics-to-web",
        "diagnostics-to-main",
        "main-to-diagnostics",
        "storage-to-main",
        "security-to-main",
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


@pytest.mark.parametrize(
    ("source", "expected_rule"),
    [
        (
            "from aiwebnovel.db import types\n",
            "domain-must-not-import-db",
        ),
        (
            "from ..db import types\n",
            "domain-must-not-import-db",
        ),
        (
            "from aiwebnovel import db\n",
            "domain-must-not-import-db",
        ),
        (
            "from aiwebnovel.core import config\n",
            "domain-must-not-import-core",
        ),
        (
            "import aiwebnovel\n",
            "domain-must-only-import-standard-library",
        ),
    ],
    ids=("absolute", "relative", "indirect-package", "core", "parent-package"),
)
def test_checker_keeps_domain_independent_from_application_layers(
    tmp_path: Path,
    source: str,
    expected_rule: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "domain/bad.py", source)

    violations = check_backend_boundaries(package_root)

    assert expected_rule in {violation.rule for violation in violations}


@pytest.mark.parametrize("framework", ["fastapi", "pydantic", "sqlalchemy"])
def test_checker_rejects_framework_imports_from_domain(
    tmp_path: Path,
    framework: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "domain/bad_framework.py", f"import {framework}\n")

    violations = check_backend_boundaries(package_root)

    assert "domain-must-not-import-frameworks" in {violation.rule for violation in violations}


def test_checker_rejects_other_third_party_packages_from_domain(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "domain/bad_dependency.py", "import third_party_package\n")

    violations = check_backend_boundaries(package_root)

    assert "domain-must-only-import-standard-library" in {
        violation.rule for violation in violations
    }


def test_checker_allows_domain_standard_library_and_db_adapter_dependency(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "domain/identifiers.py", "from dataclasses import dataclass\n")
    _write_module(
        package_root,
        "domain/revisions.py",
        "from .identifiers import Example\n",
    )
    _write_module(
        package_root,
        "db/types.py",
        "from aiwebnovel.domain.identifiers import Example\n",
    )

    assert check_backend_boundaries(package_root) == ()


def test_checker_accepts_composition_root_and_inward_dependencies(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "core/config.py", "VALUE = 1\n")
    _write_module(
        package_root,
        "storage/paths.py",
        "from aiwebnovel.core import config\n",
    )
    _write_module(
        package_root,
        "db/repository.py",
        "from aiwebnovel.core import config\nfrom aiwebnovel.storage.paths import StoragePaths\n",
    )
    _write_module(
        package_root,
        "web/frontend.py",
        "from aiwebnovel.core import config\n"
        "from aiwebnovel.security.dto import SecurityStatus\n"
        "from aiwebnovel.security.responses import security_error_response\n",
    )
    _write_module(
        package_root,
        "security/health.py",
        "from aiwebnovel.core import config\n",
    )
    _write_module(
        package_root,
        "diagnostics/checks.py",
        "from aiwebnovel.core.config import Settings\n"
        "from aiwebnovel.storage import StoragePaths\n"
        "from aiwebnovel.db import run_database_diagnostic\n"
        "from aiwebnovel.security import diagnose_security_configuration\n",
    )
    _write_module(
        package_root,
        "main.py",
        "from aiwebnovel.core import config\n"
        "from aiwebnovel.storage import paths\n"
        "from aiwebnovel.db import repository\n"
        "from aiwebnovel.security import health\n"
        "from aiwebnovel.web import frontend\n",
    )

    assert check_backend_boundaries(package_root) == ()


@pytest.mark.parametrize(
    ("source", "expected_rule"),
    [
        (
            "from aiwebnovel.core.middleware import is_valid_request_id\n",
            "diagnostics-must-use-public-core-config-contract",
        ),
        (
            "from aiwebnovel.storage.paths import StoragePaths\n",
            "diagnostics-must-use-public-storage-contract",
        ),
        (
            "from aiwebnovel.db.engine import create_database_engine\n",
            "diagnostics-must-use-public-db-contract",
        ),
        (
            "from aiwebnovel.security.health import check_security_health\n",
            "diagnostics-must-use-public-security-contract",
        ),
        (
            "from sqlalchemy import Engine\n",
            "diagnostics-must-not-import-sqlalchemy",
        ),
    ],
    ids=("core-detail", "storage-detail", "db-detail", "security-detail", "sqlalchemy"),
)
def test_checker_restricts_diagnostics_to_public_infrastructure_contracts(
    tmp_path: Path,
    source: str,
    expected_rule: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "diagnostics/bad_contract.py", source)

    violations = check_backend_boundaries(package_root)

    assert expected_rule in {violation.rule for violation in violations}


def test_checker_rejects_db_imports_of_storage_implementation_details(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "db/bad_storage_detail.py",
        "from aiwebnovel.storage.access import probe_storage_access\n",
    )
    _write_module(
        package_root,
        "db/bad_storage_package.py",
        "from aiwebnovel.storage import initialize_storage\n",
    )

    violations = check_backend_boundaries(package_root)

    storage_violations = {
        violation.path.name
        for violation in violations
        if violation.rule == "db-must-use-public-storage-paths"
    }
    assert storage_violations == {"bad_storage_detail.py", "bad_storage_package.py"}


def test_checker_rejects_web_access_to_security_session_internals(
    tmp_path: Path,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "web/bad_sessions.py",
        "from aiwebnovel.security.sessions import InMemorySessionManager\n",
    )

    violations = check_backend_boundaries(package_root)

    assert "web-must-use-public-security-contracts" in {violation.rule for violation in violations}


def test_checker_rejects_diagnostics_access_to_session_internals(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "diagnostics/bad_sessions.py",
        "from aiwebnovel.security.sessions import InMemorySessionManager\n",
    )

    violations = check_backend_boundaries(package_root)

    assert "diagnostics-must-not-access-session-internals" in {
        violation.rule for violation in violations
    }


@pytest.mark.parametrize(
    ("source", "expected_fragment"),
    [
        ("from pathlib import Path\n", "file or database persistence"),
        ("def persist() -> None:\n    open('sessions.db', 'wb')\n", "file persistence"),
    ],
    ids=("persistence-import", "file-write-call"),
)
def test_checker_keeps_session_manager_in_memory(
    tmp_path: Path,
    source: str,
    expected_fragment: str,
) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "security/sessions.py", source)

    violations = check_backend_boundaries(package_root)

    matching = [
        violation
        for violation in violations
        if violation.rule == "session-manager-must-remain-in-memory"
    ]
    assert matching
    assert expected_fragment in matching[0].message


def test_checker_keeps_localappdata_resolution_in_core_config(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "core/config.py",
        'ENVIRONMENT_NAME = "LOCALAPPDATA"\n',
    )
    _write_module(
        package_root,
        "db/bad_localappdata.py",
        'ENVIRONMENT_NAME = "LOCALAPPDATA"\n',
    )

    violations = check_backend_boundaries(package_root)

    matching = [
        violation
        for violation in violations
        if violation.rule == "localappdata-resolution-owned-by-core-config"
    ]
    assert len(matching) == 1
    assert matching[0].path.name == "bad_localappdata.py"


def test_checker_allows_non_resolving_localappdata_diagnostic_text(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "diagnostics/messages.py",
        'SUMMARY = "LocalAppData access is checked through core configuration."\n',
    )

    violations = check_backend_boundaries(package_root)

    assert "localappdata-resolution-owned-by-core-config" not in {
        violation.rule for violation in violations
    }


def test_checker_keeps_formal_data_root_derivation_in_core_config(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(
        package_root,
        "diagnostics/bad_formal_root.py",
        'formal_root = local_app_data / "AIWebNovel"\n',
    )

    violations = check_backend_boundaries(package_root)

    assert "formal-data-root-owned-by-core-config" in {violation.rule for violation in violations}


def test_checker_reports_circular_layer_dependencies(tmp_path: Path) -> None:
    package_root = _fixture_package(tmp_path)
    _write_module(package_root, "core/uses_main.py", "from aiwebnovel import main\n")
    _write_module(package_root, "main.py", "from aiwebnovel.core import uses_main\n")

    violations = check_backend_boundaries(package_root)

    assert "no-circular-layer-dependencies" in {violation.rule for violation in violations}

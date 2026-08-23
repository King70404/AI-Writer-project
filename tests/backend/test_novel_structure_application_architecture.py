"""Controlled dependency boundary checks for novel-structure application code."""

import ast
from pathlib import Path

APPLICATION_ROOT = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "src"
    / "aiwebnovel"
    / "novel_structure"
    / "application"
)
NOVEL_STRUCTURE_ROOT = APPLICATION_ROOT.parent
WEB_ROOT = NOVEL_STRUCTURE_ROOT / "web"
FORBIDDEN_ROOTS = {"alembic", "fastapi", "pydantic", "sqlalchemy"}
FORBIDDEN_AIWEBNOVEL = {
    "aiwebnovel.novel_structure.persistence",
    "aiwebnovel.novel_structure.web",
    "aiwebnovel.db",
    "aiwebnovel.web",
}


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return tuple(imports)


def test_application_has_only_declared_pure_python_dependencies() -> None:
    files = tuple(sorted(APPLICATION_ROOT.glob("*.py")))
    assert {path.name for path in files} == {
        "__init__.py",
        "commands.py",
        "mappers.py",
        "models.py",
        "queries.py",
        "services.py",
    }
    for path in files:
        for target in _imports(path):
            assert target.partition(".")[0] not in FORBIDDEN_ROOTS
            assert not any(
                target == forbidden or target.startswith(f"{forbidden}.")
                for forbidden in FORBIDDEN_AIWEBNOVEL
            )


def test_domain_repository_and_persistence_do_not_reverse_import_application() -> None:
    production_files = tuple(
        path
        for path in NOVEL_STRUCTURE_ROOT.rglob("*.py")
        if APPLICATION_ROOT not in path.parents and WEB_ROOT not in path.parents
    )
    assert production_files
    for path in production_files:
        assert not any(
            target == "aiwebnovel.novel_structure.application"
            or target.startswith("aiwebnovel.novel_structure.application.")
            for target in _imports(path)
        )


def test_controlled_illegal_framework_import_is_detected(tmp_path: Path) -> None:
    illegal = tmp_path / "illegal.py"
    illegal.write_text("from fastapi import HTTPException\n", encoding="utf-8")
    targets = _imports(illegal)
    assert targets == ("fastapi",)
    assert targets[0].partition(".")[0] in FORBIDDEN_ROOTS

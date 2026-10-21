"""Static contract checks for the RF-16 long-form evaluation wrapper."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.architecture

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPOSITORY_ROOT / "scripts" / "longform_eval.ps1"
_HARNESS = _REPOSITORY_ROOT / "scripts" / "longform_eval.py"


def _source() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def _harness() -> ModuleType:
    spec = importlib.util.spec_from_file_location("longform_eval_wrapper_contract", _HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_wrapper_requires_explicit_absolute_work_root_outside_repository() -> None:
    source = _source()

    assert re.search(r"\[Parameter\(Mandatory = \$true\)\]\s*\[string\]\$WorkRoot", source), (
        "WorkRoot must be a mandatory parameter"
    )
    assert "an explicit -WorkRoot is required" in source
    assert "Test-FullyQualifiedWindowsPath -Value $WorkRoot" in source
    assert "-WorkRoot must not be inside the source repository" in source
    assert "LOCALAPPDATA" not in source, "the wrapper must not derive a default root"
    assert "Remove-Item" not in source, "the wrapper must never delete paths"


def test_wrapper_runs_the_harness_with_the_root_virtual_environment() -> None:
    source = _source()

    assert '".venv/Scripts/python.exe"' in source
    assert '"scripts/longform_eval.py"' in source
    assert "& $pythonExecutable @arguments" in source
    assert "exit $LASTEXITCODE" in source


def test_wrapper_arguments_match_the_python_command_line() -> None:
    source = _source()
    harness = _harness()

    assert '[ValidateSet("small", "full")]' in source
    assert '[string]$Scale = "small"' in source
    assert set(harness.SCALES) == {"small", "full"}
    assert '@($evaluationScript, "--work-root", $resolvedWorkRoot, "--scale", $Scale)' in source
    assert '$arguments += "--keep-data"' in source

    for scale in ("small", "full"):
        parsed = harness.parse_arguments(
            ["--work-root", "C:\\Isolated\\Longform", "--scale", scale, "--keep-data"]
        )
        assert parsed.work_root == "C:\\Isolated\\Longform"
        assert parsed.scale == scale
        assert parsed.keep_data is True

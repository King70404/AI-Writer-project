"""Static contract checks for the author backup command-line wrapper."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aiwebnovel.backup.__main__ import _parser

pytestmark = pytest.mark.architecture

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPOSITORY_ROOT / "scripts" / "author_backup.ps1"


def _source() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_wrapper_requires_explicit_data_root_and_known_commands() -> None:
    source = _source()

    assert re.search(r"\[Parameter\(Mandatory = \$true\)\]\s*\[string\]\$DataRoot", source), (
        "DataRoot must be a mandatory parameter"
    )
    assert '[ValidateSet("create", "list", "verify", "restore")]' in source
    assert "an explicit -DataRoot is required" in source
    assert "Resolve-IsolatedDataRoot" in source
    assert "-Candidate $DataRoot" in source
    assert "LOCALAPPDATA" not in source, "the wrapper must not derive a default data root"


def test_wrapper_targets_only_the_managed_database_of_that_root() -> None:
    source = _source()

    assert "AIWEBNOVEL_DATA_ROOT = $resolvedDataRoot" in source
    assert "AIWEBNOVEL_DATABASE_URL = $null" in source
    assert '".venv/Scripts/python.exe"' in source
    assert '@("-m", "aiwebnovel.backup", $Command)' in source
    assert "restore -Target must not be inside the source repository" in source
    assert "Remove-Item" not in source, "the wrapper must never delete paths"


def test_wrapper_arguments_match_the_python_command_line() -> None:
    parser = _parser()

    for argv in (
        ["create"],
        ["list"],
        ["verify", "20261020T091500Z-0123456789ab"],
        ["restore", "20261020T091500Z-0123456789ab", "--target", "C:\\Isolated\\Copy"],
    ):
        parsed = parser.parse_args(argv)
        assert parsed.command == argv[0]

    source = _source()
    assert "$arguments += $BackupId" in source
    assert '$arguments += @($BackupId, "--target", $resolvedTarget)' in source

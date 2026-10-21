"""RF-16 long-form evaluation harness: small-scale smoke run and root isolation."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.integration

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_HARNESS = _REPOSITORY_ROOT / "scripts" / "longform_eval.py"


@pytest.fixture(scope="module")
def harness() -> Iterator[ModuleType]:
    spec = importlib.util.spec_from_file_location("longform_eval_under_test", _HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_small_scale_run_passes_and_writes_reports(
    harness: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work_root = tmp_path / "longform"

    exit_code = harness.main(["--work-root", str(work_root), "--scale", "small"])

    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert exit_code == 0
    assert summary == {
        "overall": "PASS",
        "json": "longform-report.json",
        "markdown": "longform-report.md",
    }
    report = json.loads((work_root / "longform-report.json").read_text(encoding="utf-8"))
    assert report["contract"] == "docs/LONGFORM_EVALUATION.md"
    assert report["overall"] == "PASS"
    assert report["data"]["sample"]["scale"] == "small"
    metric_ids = [metric["id"] for metric in report["metrics"]]
    assert len(metric_ids) == len(set(metric_ids))
    assert {"LE-11", "LE-12", "LE-13"} <= set(metric_ids)
    for metric in report["metrics"]:
        assert set(metric) == {"id", "name", "threshold", "measured", "passed"}
        assert metric["passed"] is not False, metric["id"]
    markdown = (work_root / "longform-report.md").read_text(encoding="utf-8")
    assert markdown.startswith("# RF-16 长篇规模评测报告")
    assert "缩小样本" in markdown
    assert sorted(path.name for path in work_root.iterdir()) == [
        "longform-report.json",
        "longform-report.md",
    ], "isolated data roots must be removed without --keep-data"


@pytest.mark.parametrize(
    "candidate",
    [
        "relative-longform-root",
        str(_REPOSITORY_ROOT),
        str(_REPOSITORY_ROOT / "work" / "longform"),
    ],
)
def test_relative_or_in_repository_work_root_is_rejected(
    harness: ModuleType, candidate: str, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = harness.main(["--work-root", candidate, "--scale", "small"])

    assert exit_code == 2
    assert "[longform]" in capsys.readouterr().err
    assert not (_REPOSITORY_ROOT / "work" / "longform").exists()
    assert not Path("relative-longform-root").exists()


def test_non_empty_work_root_is_rejected(
    harness: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "existing.txt").write_text("keep", encoding="utf-8")

    assert harness.main(["--work-root", str(tmp_path), "--scale", "small"]) == 2
    assert "new or empty folder" in capsys.readouterr().err
    assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "keep"

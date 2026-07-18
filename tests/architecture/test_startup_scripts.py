"""Deterministic safety checks for local startup orchestration scripts."""

from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = (
    "invoke_owned_process.ps1",
    "start_development.ps1",
    "start_integrated.ps1",
    "check_startup_runtime.ps1",
    "check_startup_safety.ps1",
)
_SAFETY_SCRIPT = _REPOSITORY_ROOT / "scripts" / "check_startup_safety.ps1"
_PROCESS_HELPER = _REPOSITORY_ROOT / "scripts" / "invoke_owned_process.ps1"


def _require_command(name: str) -> str:
    executable = shutil.which(name)
    assert executable is not None, f"required command is unavailable: {name}"
    return executable


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _powershell_quote(value: str | Path) -> str:
    return str(value).replace("'", "''")


def _fail_if_controlled_value_is_exposed(
    rendered: str,
    forbidden_fragments: tuple[str, ...],
) -> None:
    folded = rendered.casefold()
    if any(fragment.casefold() in folded for fragment in forbidden_fragments):
        pytest.fail(
            "startup sanitizer exposed a controlled sensitive value",
            pytrace=False,
        )


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return _run([_require_command("git"), *arguments], cwd=repository)


def _initialize_fixture(repository: Path) -> None:
    repository.mkdir()
    initialized = _git(repository, "init", "--initial-branch=main")
    assert initialized.returncode == 0, initialized.stderr
    for key, value in (
        ("user.name", "AIWebNovel Startup Test"),
        ("user.email", "startup-test@invalid.example"),
    ):
        configured = _git(repository, "config", key, value)
        assert configured.returncode == 0, configured.stderr

    scripts_directory = repository / "scripts"
    scripts_directory.mkdir()
    for name in _SCRIPTS:
        shutil.copy2(_REPOSITORY_ROOT / "scripts" / name, scripts_directory / name)
    staged = _git(repository, "add", "--all")
    assert staged.returncode == 0, staged.stderr
    committed = _git(repository, "commit", "-m", "controlled startup fixture")
    assert committed.returncode == 0, committed.stderr


def _run_safety_check(repository: Path) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            _require_command("powershell.exe"),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repository / "scripts" / _SAFETY_SCRIPT.name),
            "-RepositoryRoot",
            str(repository),
        ],
        cwd=repository,
    )


def _replace_and_stage(
    repository: Path,
    relative_path: str,
    old: str,
    new: str,
) -> None:
    path = repository / relative_path
    source = path.read_text(encoding="utf-8")
    assert old in source
    path.write_text(source.replace(old, new), encoding="utf-8")
    staged = _git(repository, "add", relative_path)
    assert staged.returncode == 0, staged.stderr


def test_tracked_startup_scripts_pass_deterministic_safety_gate(tmp_path: Path) -> None:
    repository = tmp_path / "safe-startup"
    _initialize_fixture(repository)

    result = _run_safety_check(repository)

    assert result.returncode == 0, result.stderr
    assert "deterministic startup safeguards are present" in result.stdout


def test_startup_smoke_defines_owned_child_failure_acceptance() -> None:
    helper = _PROCESS_HELPER.read_text(encoding="utf-8")
    smoke = (_REPOSITORY_ROOT / "scripts" / "check_startup_runtime.ps1").read_text(encoding="utf-8")

    assert "function Get-OwnedLoopbackListenerRecord" in helper
    assert "StartedAtUtcTicks = $listenerStartedAtUtcTicks" in helper
    assert "Test-ProcessDescendsFrom" in helper
    assert "[switch]$ExerciseChildFailure" in smoke
    assert "Stop-OwnedProcessTree -Record $frontendListenerRecord" in smoke
    assert "child_failure_detected=" in smoke
    assert "peer_cleanup=" in smoke


@pytest.mark.parametrize(
    ("relative_path", "old", "new", "expected_rule"),
    (
        (
            "scripts/invoke_owned_process.ps1",
            "StartTime.ToUniversalTime().Ticks",
            "[DateTime]::UtcNow.Ticks",
            "missing-pid-start-time-ownership-check",
        ),
        (
            "scripts/invoke_owned_process.ps1",
            "& taskkill.exe /PID $Record.ProcessId /T /F",
            "& taskkill.exe /IM node.exe /T /F",
            "forbidden-image-name-kill",
        ),
        (
            "scripts/invoke_owned_process.ps1",
            "Set-StrictMode -Version Latest",
            "Set-StrictMode -Version Latest\n& taskkill.exe /PID 1 /T /F",
            "taskkill-outside-owned-stop",
        ),
        (
            "scripts/start_development.ps1",
            "Set-StrictMode -Version Latest",
            "Set-StrictMode -Version Latest\nnpm.cmd install",
            "forbidden-dependency-install",
        ),
        (
            "scripts/start_integrated.ps1",
            "Set-StrictMode -Version Latest",
            'Set-StrictMode -Version Latest\nStart-Process "http://127.0.0.1:8000"',
            "forbidden-browser-launch",
        ),
        (
            "scripts/start_development.ps1",
            '"AIWebNovel-Development"',
            '"AIWebNovel"',
            "missing-development-data-root",
        ),
        (
            "scripts/check_startup_runtime.ps1",
            "Set-StrictMode -Version Latest",
            "Set-StrictMode -Version Latest\n$pidPath = 'service.pid'",
            "forbidden-pid-or-process-manifest",
        ),
    ),
)
def test_startup_safety_gate_rejects_controlled_violations(
    tmp_path: Path,
    relative_path: str,
    old: str,
    new: str,
    expected_rule: str,
) -> None:
    repository = tmp_path / "unsafe-startup"
    _initialize_fixture(repository)
    _replace_and_stage(repository, relative_path, old, new)

    result = _run_safety_check(repository)

    assert result.returncode == 1
    assert f"rule={expected_rule}" in result.stderr
    assert str(tmp_path) not in result.stderr


def test_startup_safety_gate_reads_unstaged_worktree_content(tmp_path: Path) -> None:
    repository = tmp_path / "unstaged-startup"
    _initialize_fixture(repository)
    path = repository / "scripts" / "start_development.ps1"
    source = path.read_text(encoding="utf-8")
    marker = "Set-StrictMode -Version Latest"
    assert marker in source
    path.write_text(
        source.replace(marker, f"{marker}\nnpm.cmd install", 1),
        encoding="utf-8",
    )

    result = _run_safety_check(repository)

    assert result.returncode == 1
    assert "rule=forbidden-dependency-install" in result.stderr
    assert str(tmp_path) not in result.stderr


def test_owned_process_rejects_mismatched_start_time_and_preserves_process() -> None:
    powershell = _require_command("powershell.exe")
    python = _REPOSITORY_ROOT / ".venv" / "Scripts" / "python.exe"
    assert python.is_file()
    helper = str(_PROCESS_HELPER).replace("'", "''")
    python_path = str(python).replace("'", "''")
    repository = str(_REPOSITORY_ROOT).replace("'", "''")
    command = f"""
. '{helper}'
$logDirectory = New-StartupLogDirectory
$record = $null
try {{
    $record = Start-OwnedProcess `
        -Name 'ownership-test' `
        -FilePath '{python_path}' `
        -ArgumentList @('-c', 'import time; time.sleep(30)') `
        -WorkingDirectory '{repository}' `
        -LogDirectory $logDirectory
    $forged = [pscustomobject]@{{
        Name = $record.Name
        Process = $record.Process
        ProcessId = $record.ProcessId
        StartedAtUtcTicks = ([long]$record.StartedAtUtcTicks + 1)
        Port = 0
        StdoutPath = $record.StdoutPath
        StderrPath = $record.StderrPath
    }}
    $rejected = $false
    try {{ Stop-OwnedProcessTree -Record $forged }} catch {{
        if ($_.Exception.Message -like 'refusing to stop a reused*') {{
            $rejected = $true
        }} else {{ throw }}
    }}
    $groupRejected = $false
    try {{ Stop-OwnedProcessGroup -Records @($forged) }} catch {{
        if ($_.Exception.Message -like 'refusing to stop a reused*') {{
            $groupRejected = $true
        }} else {{ throw }}
    }}
    if (
        -not $rejected -or
        -not $groupRejected -or
        -not (Test-OwnedProcessRunning -Record $record)
    ) {{
        throw 'mismatched identity was not safely rejected'
    }}
}} finally {{
    if ($null -ne $record) {{ Stop-OwnedProcessTree -Record $record }}
    Remove-StartupLogDirectory -Path $logDirectory
}}
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr


def test_owned_process_capture_preserves_nonzero_exit_code() -> None:
    powershell = _require_command("powershell.exe")
    helper = str(_PROCESS_HELPER).replace("'", "''")
    repository = str(_REPOSITORY_ROOT).replace("'", "''")
    command = f"""
. '{helper}'
$logDirectory = New-StartupLogDirectory
$record = $null
try {{
    $record = Start-OwnedProcess `
        -Name 'exit-code-test' `
        -FilePath '{powershell.replace("'", "''")}' `
        -ArgumentList @('-NoProfile', '-NonInteractive', '-Command', 'exit 7') `
        -WorkingDirectory '{repository}' `
        -LogDirectory $logDirectory
    $record.Process.WaitForExit()
    Complete-OwnedProcessCapture -Record $record
    if ([int]$record.Process.ExitCode -ne 7) {{
        throw 'owned process exit code was not preserved'
    }}
}} finally {{
    if ($null -ne $record) {{ Stop-OwnedProcessTree -Record $record }}
    Remove-StartupLogDirectory -Path $logDirectory
}}
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr


def test_owned_process_capture_timeout_is_bounded_and_closes_record() -> None:
    powershell = _require_command("powershell.exe")
    helper = _powershell_quote(_PROCESS_HELPER)
    command = f"""
. '{helper}'
$record = [pscustomobject]@{{
    CaptureCompleted = $false
    StdoutCaptureTask = [System.Threading.Tasks.Task]::Delay(30000)
    StderrCaptureTask = [System.Threading.Tasks.Task]::Delay(30000)
    StdoutCaptureStream = [System.IO.MemoryStream]::new()
    StderrCaptureStream = [System.IO.MemoryStream]::new()
    Process = $null
}}
$watch = [System.Diagnostics.Stopwatch]::StartNew()
$bounded = $false
try {{
    Complete-OwnedProcessCapture -Record $record -TimeoutSeconds 1
}} catch {{
    if ($_.Exception.Message -like '*bounded timeout*') {{
        $bounded = $true
    }} else {{
        throw
    }}
}} finally {{
    $watch.Stop()
}}
if (-not $bounded -or -not $record.CaptureCompleted) {{
    throw 'capture timeout was not safely finalized'
}}
if ($watch.Elapsed.TotalSeconds -gt 4) {{
    throw 'capture timeout was not bounded'
}}
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr


def test_owned_process_short_stderr_is_available_after_capture_and_cleanup() -> None:
    powershell = _require_command("powershell.exe")
    helper = _powershell_quote(_PROCESS_HELPER)
    repository = _powershell_quote(_REPOSITORY_ROOT)
    child = _powershell_quote(powershell)
    command = f"""
. '{helper}'
$logDirectory = New-StartupLogDirectory
$record = $null
try {{
    $record = Start-OwnedProcess `
        -Name 'summary-test' `
        -FilePath '{child}' `
        -ArgumentList @(
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            "[Console]::Error.WriteLine('owned-short-stderr'); exit 7"
        ) `
        -WorkingDirectory '{repository}' `
        -LogDirectory $logDirectory
    $record.Process.WaitForExit()
    Stop-OwnedProcessTree -Record $record
    Write-LimitedOwnedProcessDiagnostics -Records @($record)
}} finally {{
    if ($null -ne $record -and (Get-OwnedProcessState -Record $record) -eq 'owned') {{
        Stop-OwnedProcessTree -Record $record
    }}
    Remove-StartupLogDirectory -Path $logDirectory
}}
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr
    assert "[startup] owned-short-stderr" in result.stderr


def test_startup_failure_diagnostics_follow_process_and_port_cleanup() -> None:
    for name in (
        "start_development.ps1",
        "start_integrated.ps1",
        "check_startup_runtime.ps1",
    ):
        source = (_REPOSITORY_ROOT / "scripts" / name).read_text(encoding="utf-8")
        failure_offset = source.index("$runFailure = ConvertTo-StartupSafeText")
        finally_offset = source.index("} finally {", failure_offset)
        stop_offset = source.index("Stop-OwnedProcessGroup", finally_offset)
        release_offset = source.index("Wait-LoopbackPortReleased", stop_offset)
        diagnostics_offset = source.index(
            "Write-LimitedOwnedProcessDiagnostics",
            release_offset,
        )

        assert stop_offset < release_offset < diagnostics_offset


def test_port_conflict_probe_never_stops_the_existing_listener() -> None:
    powershell = _require_command("powershell.exe")
    helper = str(_PROCESS_HELPER).replace("'", "''")
    command = f"""
. '{helper}'
$listener = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback,
    0
)
try {{
    $listener.Server.ExclusiveAddressUse = $true
    $listener.Start()
    $port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    $rejected = $false
    try {{ Assert-LoopbackPortAvailable -Port $port }} catch {{ $rejected = $true }}
    if (-not $rejected -or -not $listener.Server.IsBound) {{
        throw 'occupied port was not rejected without disturbing its listener'
    }}
}} finally {{
    $listener.Stop()
}}
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "unsafe_line",
    (
        "Author" + "ization: Bearer startup-authorization-canary",
        "Bearer startup-bearer-canary",
        "Cook" + "ie: session=startup-cookie-canary; theme=dark",
        "Set-Cook" + "ie: session=startup-set-cookie-canary; HttpOnly",
        "X-CSRF-Token: startup-csrf-canary",
        "pass" + "word=startup-password-canary with spaces",
        "access_" + "token=startup-access-token-canary",
        "-----BEGIN " + "PRIVATE KEY----- startup-private-key-canary",
        "sk-" + "startuptoken0123456789",
    ),
    ids=(
        "authorization",
        "bearer",
        "cookie",
        "set-cookie",
        "csrf",
        "password",
        "access-token",
        "private-key",
        "standalone-token",
    ),
)
def test_startup_log_sanitizer_removes_complete_secret_values(
    unsafe_line: str,
) -> None:
    powershell = _require_command("powershell.exe")
    helper = str(_PROCESS_HELPER).replace("'", "''")
    encoded = base64.b64encode(unsafe_line.encode("utf-8")).decode("ascii")
    command = f"""
. '{helper}'
$value = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String('{encoded}')
)
ConvertTo-StartupSafeText -Value $value
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr
    _fail_if_controlled_value_is_exposed(
        result.stdout,
        ("canary", "startuptoken0123456789"),
    )
    assert "redacted" in result.stdout.casefold()


def test_startup_log_sanitizer_handles_multiline_and_extended_tokens() -> None:
    powershell = _require_command("powershell.exe")
    helper = _powershell_quote(_PROCESS_HELPER)
    unsafe = "\n".join(
        (
            "-----BEGIN " + "PRIVATE KEY-----",
            "multiline-private-canary",
            "-----END " + "PRIVATE KEY-----",
            "client_" + "secret=client-secret-canary",
            "refresh_" + "token=refresh-token-canary",
            "id_" + "token=id-token-canary",
        )
    )
    encoded = base64.b64encode(unsafe.encode("utf-8")).decode("ascii")
    command = f"""
. '{helper}'
$value = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String('{encoded}')
)
ConvertTo-StartupSafeText -Value $value
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr
    _fail_if_controlled_value_is_exposed(result.stdout, ("canary",))
    assert "redacted-private-key" in result.stdout.casefold()
    assert result.stdout.casefold().count("<redacted>") == 3


@pytest.mark.parametrize(
    "unsafe_path",
    (
        "C:" + "\\Users\\" + "Canary Name\\private\\file.txt",
        "\\\\" + "canary host\\Canary Name\\private\\file.txt",
        "file:///C:/Users/Canary Name/private/file.txt",
    ),
    ids=("drive-path", "unc-path", "file-uri"),
)
def test_startup_log_sanitizer_redacts_paths_containing_spaces(
    unsafe_path: str,
) -> None:
    powershell = _require_command("powershell.exe")
    helper = _powershell_quote(_PROCESS_HELPER)
    unsafe = f"failed at {unsafe_path}"
    encoded = base64.b64encode(unsafe.encode("utf-8")).decode("ascii")
    command = f"""
. '{helper}'
$value = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String('{encoded}')
)
ConvertTo-StartupSafeText -Value $value
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr
    _fail_if_controlled_value_is_exposed(
        result.stdout,
        ("canary", "private"),
    )
    assert "<local-path>" in result.stdout.casefold()


def test_startup_log_sanitizer_handles_unterminated_private_key() -> None:
    powershell = _require_command("powershell.exe")
    helper = _powershell_quote(_PROCESS_HELPER)
    unsafe = "\n".join(
        (
            "-----BEGIN " + "PRIVATE KEY-----",
            "unterminated-private-canary",
        )
    )
    encoded = base64.b64encode(unsafe.encode("utf-8")).decode("ascii")
    command = f"""
. '{helper}'
$value = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String('{encoded}')
)
ConvertTo-StartupSafeText -Value $value
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr
    _fail_if_controlled_value_is_exposed(result.stdout, ("canary",))
    assert "redacted-private-key" in result.stdout.casefold()


def test_frontend_build_validation_rejects_nested_reparse_point(tmp_path: Path) -> None:
    powershell = _require_command("powershell.exe")
    helper = _powershell_quote(_PROCESS_HELPER)
    repository = tmp_path / "build-reparse"
    dist = repository / "frontend" / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")
    target = tmp_path / "external-target"
    target.mkdir()
    junction = assets / "nested-link"
    command = f"""
. '{helper}'
$junction = New-Item `
    -ItemType Junction `
    -Path '{_powershell_quote(junction)}' `
    -Target '{_powershell_quote(target)}'
try {{
    $rejected = $false
    try {{
        Assert-FrontendBuild `
            -DistPath '{_powershell_quote(dist)}' `
            -RepositoryRoot '{_powershell_quote(repository)}'
    }} catch {{
        if ($_.Exception.Message -like '*reparse point*') {{
            $rejected = $true
        }} else {{
            throw
        }}
    }}
    if (-not $rejected) {{ throw 'nested reparse point was accepted' }}
}} finally {{
    if (Test-Path -LiteralPath $junction.FullName) {{
        [System.IO.Directory]::Delete($junction.FullName, $false)
    }}
}}
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr


def test_frontend_build_validation_rejects_prohibited_content(tmp_path: Path) -> None:
    powershell = _require_command("powershell.exe")
    helper = _powershell_quote(_PROCESS_HELPER)
    repository = tmp_path / "build-content"
    dist = repository / "frontend" / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    asset = assets / "app.js"
    asset.write_text("console.log('ok')", encoding="utf-8")
    valid_command = f"""
. '{helper}'
Assert-FrontendBuild `
    -DistPath '{_powershell_quote(dist)}' `
    -RepositoryRoot '{_powershell_quote(repository)}'
"""
    valid = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", valid_command],
        cwd=_REPOSITORY_ROOT,
    )
    assert valid.returncode == 0, valid.stderr

    invalid_command = f"""
. '{helper}'
$rejected = $false
try {{
    Assert-FrontendBuild `
        -DistPath '{_powershell_quote(dist)}' `
        -RepositoryRoot '{_powershell_quote(repository)}'
}} catch {{
    if ($_.Exception.Message -like '*prohibited*') {{
        $rejected = $true
    }} else {{
        throw
    }}
}}
if (-not $rejected) {{ throw 'prohibited build content was accepted' }}
"""
    prohibited_payloads = (
        "const localPath = " + repr("C:" + "\\private\\frontend-source.ts"),
        "const access_" + "token = 'startupcredentialcanary'",
        "const networkPath = " + repr("\\\\server\\share\\frontend.js"),
    )
    for payload in prohibited_payloads:
        asset.write_text(payload, encoding="utf-8")
        invalid = _run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                invalid_command,
            ],
            cwd=_REPOSITORY_ROOT,
        )

        assert invalid.returncode == 0, invalid.stderr


def test_integrated_build_preserves_existing_dist_and_revalidates() -> None:
    source = (_REPOSITORY_ROOT / "scripts" / "start_integrated.ps1").read_text(encoding="utf-8")
    build_offset = source.index("if ($BuildFrontend)")
    boundary_offset = source.index("Assert-FrontendBuildBoundary")
    validation_offset = source.index("Assert-FrontendBuild", build_offset + 1)

    assert boundary_offset < build_offset < validation_offset
    assert '@("run", "build", "--", "--", "--emptyOutDir", "false")' in source
    assert "npm install" not in source.casefold()


def test_process_ancestry_query_requests_only_required_fields() -> None:
    helper = _PROCESS_HELPER.read_text(encoding="utf-8")
    ancestry_start = helper.index("function Test-ProcessDescendsFrom")
    ancestry_end = helper.index("function Get-OwnedLoopbackListenerRecord")
    ancestry = helper[ancestry_start:ancestry_end]

    assert "SELECT ProcessId, ParentProcessId FROM Win32_Process" in ancestry
    assert "-ClassName Win32_Process" not in ancestry
    assert "CommandLine" not in ancestry


def test_data_root_rejects_formal_repository_and_reparse_overlap(tmp_path: Path) -> None:
    powershell = _require_command("powershell.exe")
    helper = str(_PROCESS_HELPER).replace("'", "''")
    repository = str(_REPOSITORY_ROOT).replace("'", "''")
    repository_parent = str(_REPOSITORY_ROOT.parent).replace("'", "''")
    test_root = str(tmp_path).replace("'", "''")
    command = f"""
. '{helper}'
$localAppData = [Environment]::GetEnvironmentVariable('LOCALAPPDATA', 'Process')
$rejected = 0
foreach ($candidate in @($localAppData, '{repository}', '{repository_parent}')) {{
    try {{
        $null = Resolve-IsolatedDataRoot `
            -Candidate $candidate `
            -DefaultLeaf 'unused' `
            -RepositoryRoot '{repository}'
    }} catch {{ $rejected += 1 }}
}}
if ($rejected -ne 3) {{ throw 'a protected data-root overlap was accepted' }}

$target = Join-Path '{test_root}' 'junction-target'
$junction = Join-Path '{test_root}' 'junction-path'
New-Item -ItemType Directory -Path $target | Out-Null
New-Item -ItemType Junction -Path $junction -Target $target | Out-Null
try {{
    $reparseRejected = $false
    try {{
        $null = Resolve-IsolatedDataRoot `
            -Candidate (Join-Path $junction 'child') `
            -DefaultLeaf 'unused' `
            -RepositoryRoot '{repository}'
    }} catch {{
        if ($_.Exception.Message -like '*reparse point*') {{
            $reparseRejected = $true
        }} else {{ throw }}
    }}
    if (-not $reparseRejected) {{ throw 'reparse traversal was accepted' }}
}} finally {{
    Remove-Item -LiteralPath $junction -Force
}}
"""

    result = _run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
    )

    assert result.returncode == 0, result.stderr

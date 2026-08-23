[CmdletBinding()]
param(
    [ValidateSet("Development", "Integrated", "All")]
    [string]$Mode = "All",
    [string]$Scenario = "",
    [switch]$Headed,
    [ValidateRange(0, 65535)]
    [int]$ProxyBackendPort = 0,
    [switch]$SimulateStartupInterruption
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$script:FrontendRoot = Join-Path $script:RepositoryRoot "frontend"
$script:RuntimeRoot = Join-Path $script:RepositoryRoot ".runtime/e2e"
$script:ServiceLauncher = Join-Path $PSScriptRoot "run_e2e_service.ps1"
$script:PlaywrightExecutable = Join-Path (
    $script:FrontendRoot
) "node_modules/.bin/playwright.cmd"

function Assert-SafeContainedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [Parameter(Mandatory = $true)]
        [string]$Container,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    $fullCandidate = [System.IO.Path]::GetFullPath($Candidate)
    $fullContainer = [System.IO.Path]::GetFullPath($Container).TrimEnd("\", "/")
    if (Test-Path -LiteralPath $fullContainer) {
        $containerItem = Get-Item -LiteralPath $fullContainer -Force
        if (($containerItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Description controlled root must not be a reparse point"
        }
    }
    $requiredPrefix = "$fullContainer$([System.IO.Path]::DirectorySeparatorChar)"
    if (-not $fullCandidate.StartsWith(
            $requiredPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "$Description must stay inside its controlled root"
    }

    $relativePath = $fullCandidate.Substring($requiredPrefix.Length)
    $currentPath = $fullContainer
    foreach ($segment in $relativePath.Split(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.StringSplitOptions]::RemoveEmptyEntries
        )) {
        $currentPath = Join-Path $currentPath $segment
        if (-not (Test-Path -LiteralPath $currentPath)) {
            continue
        }
        $item = Get-Item -LiteralPath $currentPath -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Description must not traverse a reparse point"
        }
    }
}

function Assert-E2ERunDirectoryIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RunDirectory
    )

    $fullRunDirectory = [System.IO.Path]::GetFullPath($RunDirectory)
    $runtimeRoot = [System.IO.Path]::GetFullPath($script:RuntimeRoot)
    $runParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $fullRunDirectory))
    if (-not $runParent.Equals(
            $runtimeRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "E2E run directory must be a direct child of its controlled root"
    }
    $runName = Split-Path -Leaf $fullRunDirectory
    if ($runName -notmatch '^e2e-(?:dev|int|startup)-\d{3}-\d+-[0-9a-f]{32}$') {
        throw "E2E run directory must carry its exact ownership marker"
    }
}

function Assert-E2EDataRootIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot,
        [Parameter(Mandatory = $true)]
        [string]$RunDirectory
    )

    Assert-E2ERunDirectoryIdentity -RunDirectory $RunDirectory
    Assert-SafeContainedPath `
        -Candidate $DataRoot `
        -Container $RunDirectory `
        -Description "E2E data root"
    $fullDataRoot = [System.IO.Path]::GetFullPath($DataRoot)
    $dataRootParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $fullDataRoot))
    if (-not $dataRootParent.Equals(
            [System.IO.Path]::GetFullPath($RunDirectory),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "E2E data root must be a direct child of its run directory"
    }
    $dataRootName = Split-Path -Leaf $fullDataRoot
    if ($dataRootName -notmatch '^AIWebNovel-E2E-DataRoot-[0-9a-f]{32}$') {
        throw "E2E data root must carry its exact ownership marker"
    }
}

function Assert-NoReparsePointsInTree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    $fullRoot = [System.IO.Path]::GetFullPath($Root)
    if (-not (Test-Path -LiteralPath $fullRoot -PathType Container)) {
        throw "$Description is not an existing directory"
    }
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($fullRoot)
    while ($pending.Count -gt 0) {
        $currentDirectory = $pending.Pop()
        $directoryItem = Get-Item -LiteralPath $currentDirectory -Force
        if (
            ($directoryItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            throw "$Description must not contain a reparse point"
        }
        foreach ($item in Get-ChildItem -LiteralPath $currentDirectory -Force) {
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "$Description must not contain a reparse point"
            }
            if ($item.PSIsContainer) {
                $pending.Push($item.FullName)
            }
        }
    }
}

function Assert-E2EStorageLayout {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot,
        [Parameter(Mandatory = $true)]
        [string]$RunDirectory,
        [Parameter(Mandatory = $true)]
        [string]$ScenarioName
    )

    Assert-E2EDataRootIdentity -DataRoot $DataRoot -RunDirectory $RunDirectory
    Assert-NoReparsePointsInTree -Root $DataRoot -Description "E2E data root"
    foreach ($relativePath in @(
            "data",
            "assets",
            "runtime",
            "runtime/app",
            "runtime/temp",
            "runtime/locks",
            "models",
            "backups",
            "exports",
            "logs",
            "config"
        )) {
        $directory = Join-Path $DataRoot $relativePath
        Assert-SafeContainedPath `
            -Candidate $directory `
            -Container $DataRoot `
            -Description "E2E storage directory"
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
            throw "E2E storage initialization did not create every standard directory"
        }
    }

    $databasePath = Join-Path $DataRoot "data/aiwebnovel.sqlite3"
    Assert-SafeContainedPath `
        -Candidate $databasePath `
        -Container $DataRoot `
        -Description "E2E derived database"
    if (-not (Test-Path -LiteralPath $databasePath -PathType Leaf)) {
        throw "E2E database was not derived inside the data directory"
    }
    $databaseItem = Get-Item -LiteralPath $databasePath -Force
    if (($databaseItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "E2E derived database must not be a reparse point"
    }

    $formerDatabaseFile = Join-Path $RunDirectory "$ScenarioName.sqlite3"
    if (Test-Path -LiteralPath $formerDatabaseFile) {
        throw "E2E database must not use the former run-directory location"
    }
}

function Assert-ProjectFrontendDatabaseCounts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot
    )

    $databasePath = Join-Path $DataRoot "data/aiwebnovel.sqlite3"
    Assert-SafeContainedPath `
        -Candidate $databasePath `
        -Container $DataRoot `
        -Description "Project frontend E2E database"
    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    $query = @'
import json
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
try:
    names = ('projects', 'project_heads', 'project_revisions')
    counts = {name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in names}
    print(json.dumps(counts))
finally:
    connection.close()
'@
    $output = & $pythonExecutable -c $query $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Project frontend E2E database count verification failed"
    }
    try {
        $counts = $output | ConvertFrom-Json
    } catch {
        throw "Project frontend E2E database count output was invalid"
    }
    foreach ($name in @("projects", "project_heads", "project_revisions")) {
        if ([int]$counts.$name -ne 21) {
            throw "Project frontend E2E expected 21 rows in $name"
        }
    }
}

function Assert-ProjectDetailDatabaseState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot
    )

    $databasePath = Join-Path $DataRoot "data/aiwebnovel.sqlite3"
    Assert-SafeContainedPath `
        -Candidate $databasePath `
        -Container $DataRoot `
        -Description "Project detail E2E database"
    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    $query = @'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
try:
    counts = {
        name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
        for name in ('projects', 'project_heads', 'project_revisions')
    }
    assert counts == {'projects': 2, 'project_heads': 2, 'project_revisions': 5}

    projects = connection.execute(
        '''
        SELECT p.id, p.concurrency_version, h.revision_id,
               current_revision.revision_number, current_revision.title
        FROM projects AS p
        JOIN project_heads AS h ON h.project_id = p.id
        JOIN project_revisions AS current_revision
          ON current_revision.project_id = h.project_id
         AND current_revision.id = h.revision_id
        ORDER BY current_revision.title
        '''
    ).fetchall()
    by_title = {row[4]: row for row in projects}
    direct = by_title['E2E Project Detail Direct Revised 009']
    conflict = by_title['E2E Project Conflict Local Draft 009']
    assert direct[1] == 2 and direct[3] == 2
    assert conflict[1] == 3 and conflict[3] == 3

    direct_revisions = connection.execute(
        '''
        SELECT revision_number, id, title, description
        FROM project_revisions
        WHERE project_id = ?
        ORDER BY revision_number
        ''',
        (direct[0],),
    ).fetchall()
    assert direct_revisions == [
        (1, direct_revisions[0][1], 'E2E Project Detail Direct Initial 009',
         'E2E-PROJECT-DETAIL-DIRECT-INITIAL-DESCRIPTION-CANARY-009'),
        (2, direct_revisions[1][1], 'E2E Project Detail Direct Revised 009',
         'E2E-PROJECT-DETAIL-DIRECT-REVISED-DESCRIPTION-CANARY-009'),
    ]
    assert len({row[1] for row in direct_revisions}) == 2
    assert direct[2] == direct_revisions[-1][1]

    conflict_revisions = connection.execute(
        '''
        SELECT revision_number, id, title, description
        FROM project_revisions
        WHERE project_id = ?
        ORDER BY revision_number
        ''',
        (conflict[0],),
    ).fetchall()
    assert len(conflict_revisions) == 3
    assert [row[0] for row in conflict_revisions] == [1, 2, 3]
    assert [row[2] for row in conflict_revisions] == [
        'E2E Project Conflict Initial 009',
        'E2E Project Conflict External 009',
        'E2E Project Conflict Local Draft 009',
    ]
    assert conflict_revisions[0][3] == 'E2E-PROJECT-CONFLICT-INITIAL-DESCRIPTION-CANARY-009'
    assert conflict_revisions[1][3] == 'E2E-PROJECT-CONFLICT-EXTERNAL-DESCRIPTION-CANARY-009'
    assert conflict_revisions[2][3] == (
        'E2E-PROJECT-CONFLICT-LOCAL-DESCRIPTION-CANARY-009\n'
        '\u4fdd\u7559\u6362\u884c'
    )
    assert len({row[1] for row in conflict_revisions}) == 3
    assert conflict[2] == conflict_revisions[-1][1]
finally:
    connection.close()
'@
    & $pythonExecutable -c $query $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Project detail E2E database state verification failed"
    }
}

function Assert-ProjectRevisionHistoryDatabaseState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot
    )

    $databasePath = Join-Path $DataRoot "data/aiwebnovel.sqlite3"
    Assert-SafeContainedPath `
        -Candidate $databasePath `
        -Container $DataRoot `
        -Description "Project revision history E2E database"
    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    $query = @'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
try:
    counts = {
        name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
        for name in ('projects', 'project_heads', 'project_revisions')
    }
    assert counts == {'projects': 1, 'project_heads': 1, 'project_revisions': 21}
    project_id, concurrency_version = connection.execute(
        'SELECT id, concurrency_version FROM projects'
    ).fetchone()
    assert concurrency_version == 21
    head_revision_id = connection.execute(
        'SELECT revision_id FROM project_heads WHERE project_id = ?',
        (project_id,),
    ).fetchone()[0]
    revisions = connection.execute(
        '''
        SELECT revision_number, id, title, description, created_at
        FROM project_revisions
        WHERE project_id = ?
        ORDER BY revision_number
        ''',
        (project_id,),
    ).fetchall()
    assert [row[0] for row in revisions] == list(range(1, 22))
    assert len({row[1] for row in revisions}) == 21
    assert head_revision_id == revisions[-1][1]
    assert revisions[0][2:4] == (
        'E2E Project History Revision 01 010',
        'E2E-PROJECT-HISTORY-DESCRIPTION-CANARY-010-REVISION-01',
    )
    assert revisions[1][2:4] == (
        'E2E Project History Revision 02 010',
        'E2E-PROJECT-HISTORY-DESCRIPTION-CANARY-010-REVISION-02\n\u7b2c\u4e8c\u884c',
    )
    assert revisions[2][2:4] == (
        'E2E Project History Revision 03 010',
        'E2E-PROJECT-HISTORY-DESCRIPTION-CANARY-010-REVISION-03',
    )
    trigger_names = {
        row[0]
        for row in connection.execute(
            '''SELECT name FROM sqlite_master WHERE type = 'trigger' '''
        )
    }
    assert {
        'trg_project_revisions_no_update',
        'trg_project_revisions_no_delete',
    }.issubset(trigger_names)
    for statement in (
        'UPDATE project_revisions SET title = title WHERE revision_number = 1',
        'DELETE FROM project_revisions WHERE revision_number = 1',
    ):
        try:
            connection.execute(statement)
        except sqlite3.IntegrityError as error:
            assert 'immutable' in str(error).lower()
            connection.rollback()
        else:
            raise AssertionError('immutable Project revision trigger did not reject a write')
    unchanged = connection.execute(
        '''
        SELECT title, description, created_at
        FROM project_revisions
        WHERE project_id = ? AND revision_number = 1
        ''',
        (project_id,),
    ).fetchone()
    assert unchanged == (revisions[0][2], revisions[0][3], revisions[0][4])
finally:
    connection.close()
'@
    & $pythonExecutable -c $query $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Project revision history E2E database state verification failed"
    }
}

function Assert-StoryBibleHttpDatabaseState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot
    )

    $databasePath = Join-Path $DataRoot "data/aiwebnovel.sqlite3"
    Assert-SafeContainedPath `
        -Candidate $databasePath `
        -Container $DataRoot `
        -Description "Story Bible HTTP E2E database"
    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    $query = @'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
try:
    counts = {
        name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
        for name in (
            'projects',
            'project_heads',
            'project_revisions',
            'story_bibles',
            'story_bible_heads',
            'story_bible_revisions',
        )
    }
    assert counts == {
        'projects': 1,
        'project_heads': 1,
        'project_revisions': 1,
        'story_bibles': 1,
        'story_bible_heads': 1,
        'story_bible_revisions': 3,
    }

    project_id, project_version = connection.execute(
        'SELECT id, concurrency_version FROM projects'
    ).fetchone()
    assert project_version == 1
    story_bible_id, owner_id, story_bible_version = connection.execute(
        'SELECT id, project_id, concurrency_version FROM story_bibles'
    ).fetchone()
    assert owner_id == project_id
    assert story_bible_version == 3
    head_revision_id = connection.execute(
        'SELECT revision_id FROM story_bible_heads WHERE story_bible_id = ?',
        (story_bible_id,),
    ).fetchone()[0]
    revisions = connection.execute(
        '''
        SELECT revision_number, id, title, content, created_at
        FROM story_bible_revisions
        WHERE story_bible_id = ?
        ORDER BY revision_number
        ''',
        (story_bible_id,),
    ).fetchall()
    assert [row[0] for row in revisions] == [1, 2, 3]
    assert len({row[1] for row in revisions}) == 3
    assert revisions[0][2:4] == ('Initial Story Bible', 'Line A\nLine B')
    assert revisions[1][2:4] == ('Replacement Story Bible', '')
    assert revisions[2][2:4] in {
        (
            'E2E-STORY-BIBLE-TITLE-CANARY-011-A',
            'E2E-STORY-BIBLE-CONTENT-CANARY-011-A',
        ),
        (
            'E2E-STORY-BIBLE-TITLE-CANARY-011-B',
            'E2E-STORY-BIBLE-CONTENT-CANARY-011-B',
        ),
    }
    assert head_revision_id == revisions[2][1]

    trigger_names = {
        row[0]
        for row in connection.execute(
            '''SELECT name FROM sqlite_master WHERE type = 'trigger' '''
        )
    }
    assert {
        'trg_story_bible_revisions_no_update',
        'trg_story_bible_revisions_no_delete',
    }.issubset(trigger_names)
    for statement in (
        'UPDATE story_bible_revisions SET title = title WHERE revision_number = 1',
        'DELETE FROM story_bible_revisions WHERE revision_number = 1',
    ):
        try:
            connection.execute(statement)
        except sqlite3.IntegrityError as error:
            assert 'immutable' in str(error).lower()
            connection.rollback()
        else:
            raise AssertionError('immutable Story Bible revision trigger did not reject a write')
    unchanged = connection.execute(
        '''
        SELECT title, content, created_at
        FROM story_bible_revisions
        WHERE story_bible_id = ? AND revision_number = 1
        ''',
        (story_bible_id,),
    ).fetchone()
    assert unchanged == (revisions[0][2], revisions[0][3], revisions[0][4])
finally:
    connection.close()
'@
    & $pythonExecutable -c $query $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Story Bible HTTP E2E database state verification failed"
    }
}

function Assert-StoryBibleFrontendDatabaseState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot
    )

    $databasePath = Join-Path $DataRoot "data/aiwebnovel.sqlite3"
    Assert-SafeContainedPath `
        -Candidate $databasePath `
        -Container $DataRoot `
        -Description "Story Bible frontend E2E database"
    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    $query = @'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
try:
    counts = {
        name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
        for name in (
            'projects',
            'project_heads',
            'project_revisions',
            'story_bibles',
            'story_bible_heads',
            'story_bible_revisions',
        )
    }
    assert counts == {
        'projects': 1,
        'project_heads': 1,
        'project_revisions': 1,
        'story_bibles': 1,
        'story_bible_heads': 1,
        'story_bible_revisions': 4,
    }

    project_id, project_version = connection.execute(
        'SELECT id, concurrency_version FROM projects'
    ).fetchone()
    assert project_version == 1
    project_revision = connection.execute(
        '''
        SELECT revision_number, title, description
        FROM project_revisions
        WHERE project_id = ?
        ''',
        (project_id,),
    ).fetchone()
    assert project_revision == (
        1,
        'E2E Story Bible Frontend Owner 012',
        'E2E-STORY-BIBLE-PROJECT-DESCRIPTION-CANARY-012',
    )

    story_bible_id, owner_id, story_bible_version = connection.execute(
        'SELECT id, project_id, concurrency_version FROM story_bibles'
    ).fetchone()
    assert owner_id == project_id
    assert story_bible_version == 4
    head_revision_id = connection.execute(
        'SELECT revision_id FROM story_bible_heads WHERE story_bible_id = ?',
        (story_bible_id,),
    ).fetchone()[0]
    revisions = connection.execute(
        '''
        SELECT revision_number, id, title, content, created_at
        FROM story_bible_revisions
        WHERE story_bible_id = ?
        ORDER BY revision_number
        ''',
        (story_bible_id,),
    ).fetchall()
    assert [row[0] for row in revisions] == [1, 2, 3, 4]
    assert len({row[1] for row in revisions}) == 4
    assert [row[2:4] for row in revisions] == [
        (
            'E2E Story Bible UI Initial 012',
            'E2E-STORY-BIBLE-UI-CONTENT-CANARY-012-V1\nsecond line',
        ),
        (
            'E2E Story Bible UI Revised 012',
            'E2E-STORY-BIBLE-UI-CONTENT-CANARY-012-V2\nreplacement',
        ),
        (
            'E2E Story Bible External 012',
            'E2E-STORY-BIBLE-UI-CONTENT-CANARY-012-V3',
        ),
        (
            'E2E Story Bible Local Rebased 012',
            'E2E-STORY-BIBLE-UI-CONTENT-CANARY-012-V4\npreserved draft',
        ),
    ]
    assert head_revision_id == revisions[3][1]

    trigger_names = {
        row[0]
        for row in connection.execute(
            '''SELECT name FROM sqlite_master WHERE type = 'trigger' '''
        )
    }
    assert {
        'trg_story_bible_revisions_no_update',
        'trg_story_bible_revisions_no_delete',
    }.issubset(trigger_names)
    for statement in (
        'UPDATE story_bible_revisions SET title = title WHERE revision_number = 1',
        'DELETE FROM story_bible_revisions WHERE revision_number = 1',
    ):
        try:
            connection.execute(statement)
        except sqlite3.IntegrityError as error:
            assert 'immutable' in str(error).lower()
            connection.rollback()
        else:
            raise AssertionError('immutable Story Bible revision trigger did not reject a write')
    unchanged = connection.execute(
        '''
        SELECT title, content, created_at
        FROM story_bible_revisions
        WHERE story_bible_id = ? AND revision_number = 1
        ''',
        (story_bible_id,),
    ).fetchone()
    assert unchanged == (revisions[0][2], revisions[0][3], revisions[0][4])
finally:
    connection.close()
'@
    & $pythonExecutable -c $query $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Story Bible frontend E2E database state verification failed"
    }
}

function Assert-StoryBibleRevisionHistoryDatabaseState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot
    )

    $databasePath = Join-Path $DataRoot "data/aiwebnovel.sqlite3"
    Assert-SafeContainedPath `
        -Candidate $databasePath `
        -Container $DataRoot `
        -Description "Story Bible revision history E2E database"
    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    $query = @'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
try:
    counts = {
        name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
        for name in (
            'projects',
            'project_heads',
            'project_revisions',
            'story_bibles',
            'story_bible_heads',
            'story_bible_revisions',
        )
    }
    assert counts == {
        'projects': 1,
        'project_heads': 1,
        'project_revisions': 1,
        'story_bibles': 1,
        'story_bible_heads': 1,
        'story_bible_revisions': 21,
    }
    story_bible_id, version = connection.execute(
        'SELECT id, concurrency_version FROM story_bibles'
    ).fetchone()
    assert version == 21
    revisions = connection.execute(
        '''
        SELECT revision_number, id, title, content
        FROM story_bible_revisions
        WHERE story_bible_id = ?
        ORDER BY revision_number
        ''',
        (story_bible_id,),
    ).fetchall()
    assert [row[0] for row in revisions] == list(range(1, 22))
    assert len({row[1] for row in revisions}) == 21
    assert revisions[0][2:] == (
        'E2E Story Bible History Revision 01 013',
        'E2E-STORY-BIBLE-HISTORY-CONTENT-CANARY-013-01',
    )
    assert revisions[-1][2:] == (
        'E2E Story Bible History Revision 21 013',
        'E2E-STORY-BIBLE-HISTORY-CONTENT-CANARY-013-21',
    )
    head = connection.execute(
        'SELECT revision_id FROM story_bible_heads WHERE story_bible_id = ?',
        (story_bible_id,),
    ).fetchone()[0]
    assert head == revisions[-1][1]
finally:
    connection.close()
'@
    & $pythonExecutable -c $query $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Story Bible revision history E2E database state verification failed"
    }
}

function Assert-CharacterHttpDatabaseState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot
    )

    $databasePath = Join-Path $DataRoot "data/aiwebnovel.sqlite3"
    Assert-SafeContainedPath `
        -Candidate $databasePath `
        -Container $DataRoot `
        -Description "Character HTTP E2E database"
    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    $query = @'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
try:
    counts = {
        name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
        for name in (
            'projects',
            'project_heads',
            'project_revisions',
            'story_bibles',
            'story_bible_heads',
            'story_bible_revisions',
            'characters',
            'character_heads',
            'character_revisions',
        )
    }
    assert counts == {
        'projects': 1,
        'project_heads': 1,
        'project_revisions': 1,
        'story_bibles': 0,
        'story_bible_heads': 0,
        'story_bible_revisions': 0,
        'characters': 2,
        'character_heads': 2,
        'character_revisions': 4,
    }
    project_version = connection.execute(
        'SELECT concurrency_version FROM projects'
    ).fetchone()[0]
    assert project_version == 1
    rows = connection.execute(
        '''
        SELECT c.id, c.concurrency_version, h.revision_id
        FROM characters AS c
        JOIN character_heads AS h ON h.character_id = c.id
        ORDER BY c.id
        '''
    ).fetchall()
    assert sorted(row[1] for row in rows) == [1, 3]
    revised_id = next(row[0] for row in rows if row[1] == 3)
    revisions = connection.execute(
        '''
        SELECT id, revision_number, name, role, profile
        FROM character_revisions
        WHERE character_id = ?
        ORDER BY revision_number
        ''',
        (revised_id,),
    ).fetchall()
    assert [row[1] for row in revisions] == [1, 2, 3]
    assert revisions[0][2:] == (
        'Shared Character',
        'Lead',
        'E2E-CHARACTER-PROFILE-CANARY-014-A',
    )
    revised_head = next(row[2] for row in rows if row[0] == revised_id)
    assert revised_head == revisions[-1][0]
    for statement in (
        'UPDATE character_revisions SET name = name WHERE revision_number = 1',
        'DELETE FROM character_revisions WHERE revision_number = 1',
    ):
        try:
            connection.execute(statement)
        except sqlite3.IntegrityError as error:
            assert 'immutable' in str(error).lower()
            connection.rollback()
        else:
            raise AssertionError('immutable Character revision trigger did not reject a write')
finally:
    connection.close()
'@
    & $pythonExecutable -c $query $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Character HTTP E2E database state verification failed"
    }
}

function Assert-CharacterFrontendDatabaseState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot
    )

    $databasePath = Join-Path $DataRoot "data/aiwebnovel.sqlite3"
    Assert-SafeContainedPath `
        -Candidate $databasePath `
        -Container $DataRoot `
        -Description "Character frontend E2E database"
    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    $query = @'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
try:
    counts = {
        name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
        for name in (
            'projects', 'project_heads', 'project_revisions',
            'story_bibles', 'story_bible_heads', 'story_bible_revisions',
            'characters', 'character_heads', 'character_revisions',
        )
    }
    assert counts == {
        'projects': 1,
        'project_heads': 1,
        'project_revisions': 1,
        'story_bibles': 0,
        'story_bible_heads': 0,
        'story_bible_revisions': 0,
        'characters': 2,
        'character_heads': 2,
        'character_revisions': 5,
    }
    assert connection.execute(
        'SELECT concurrency_version FROM projects'
    ).fetchone()[0] == 1
    rows = connection.execute(
        '''
        SELECT c.id, c.concurrency_version, h.revision_id
        FROM characters AS c
        JOIN character_heads AS h ON h.character_id = c.id
        ORDER BY c.id
        '''
    ).fetchall()
    assert sorted(row[1] for row in rows) == [1, 4]
    revised_id = next(row[0] for row in rows if row[1] == 4)
    revised_head = next(row[2] for row in rows if row[0] == revised_id)
    revisions = connection.execute(
        '''
        SELECT id, revision_number, name, role, profile
        FROM character_revisions
        WHERE character_id = ?
        ORDER BY revision_number
        ''',
        (revised_id,),
    ).fetchall()
    assert [row[1] for row in revisions] == [1, 2, 3, 4]
    assert [row[4] for row in revisions] == [
        'E2E-CHARACTER-PROFILE-CANARY-015-A\nprivate line',
        'E2E-CHARACTER-PROFILE-CANARY-015-A-V2',
        'E2E-CHARACTER-PROFILE-CANARY-015-A-V3',
        'E2E-CHARACTER-PROFILE-CANARY-015-A-V4-LOCAL',
    ]
    assert revised_head == revisions[-1][0]
finally:
    connection.close()
'@
    & $pythonExecutable -c $query $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Character frontend E2E database state verification failed"
    }
}

function Assert-CharacterRevisionHistoryDatabaseState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataRoot
    )

    $databasePath = Join-Path $DataRoot "data/aiwebnovel.sqlite3"
    Assert-SafeContainedPath `
        -Candidate $databasePath `
        -Container $DataRoot `
        -Description "Character revision history E2E database"
    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    $query = @'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
try:
    counts = {
        name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
        for name in (
            'projects', 'project_heads', 'project_revisions',
            'story_bibles', 'story_bible_heads', 'story_bible_revisions',
            'characters', 'character_heads', 'character_revisions',
        )
    }
    assert counts == {
        'projects': 1,
        'project_heads': 1,
        'project_revisions': 1,
        'story_bibles': 0,
        'story_bible_heads': 0,
        'story_bible_revisions': 0,
        'characters': 1,
        'character_heads': 1,
        'character_revisions': 21,
    }
    assert connection.execute(
        'SELECT concurrency_version FROM projects'
    ).fetchone()[0] == 1
    character_id, version = connection.execute(
        'SELECT id, concurrency_version FROM characters'
    ).fetchone()
    assert version == 21
    revisions = connection.execute(
        '''
        SELECT id, revision_number, name, role, profile
        FROM character_revisions
        WHERE character_id = ?
        ORDER BY revision_number
        ''',
        (character_id,),
    ).fetchall()
    assert [row[1] for row in revisions] == list(range(1, 22))
    assert len({row[0] for row in revisions}) == 21
    assert revisions[0][2:] == (
        'E2E Character History 016 01',
        'Lead 01',
        'E2E-CHARACTER-HISTORY-PROFILE-CANARY-016-01\nline two',
    )
    assert revisions[-1][2:] == (
        'E2E Character History 016 21',
        'Lead 21',
        'E2E-CHARACTER-HISTORY-PROFILE-CANARY-016-21',
    )
    head = connection.execute(
        'SELECT revision_id FROM character_heads WHERE character_id = ?',
        (character_id,),
    ).fetchone()[0]
    assert head == revisions[-1][0]
finally:
    connection.close()
'@
    & $pythonExecutable -c $query $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Character revision history E2E database state verification failed"
    }
}

function Test-LoopbackPortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int]$Port
    )

    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $Port
    )
    try {
        $listener.Server.ExclusiveAddressUse = $true
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        $listener.Stop()
    }
}

function Assert-PortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    if (-not (Test-LoopbackPortAvailable -Port $Port)) {
        throw "E2E port $Port is already in use; existing services are never reused"
    }
}

function Wait-PortReleased {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [int]$TimeoutSeconds = 10
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (Test-LoopbackPortAvailable -Port $Port) {
            return
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "owned E2E port $Port was not released"
}

function Assert-ServiceOwnsPort {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ServiceRecord
    )

    $listeners = @(
        Get-NetTCPConnection `
            -State Listen `
            -LocalAddress "127.0.0.1" `
            -LocalPort $ServiceRecord.Port `
            -ErrorAction SilentlyContinue
    )
    $ownerIsRecordedDescendant = $false
    if ($listeners.Count -eq 1) {
        $candidateProcessId = [int]$listeners[0].OwningProcess
        for ($depth = 0; $depth -lt 32 -and $candidateProcessId -gt 0; $depth++) {
            if ($candidateProcessId -eq $ServiceRecord.ServiceProcessId) {
                $ownerIsRecordedDescendant = $true
                break
            }
            $candidate = Get-CimInstance `
                -ClassName Win32_Process `
                -Filter "ProcessId = $candidateProcessId" `
                -ErrorAction SilentlyContinue
            if ($null -eq $candidate) {
                break
            }
            $candidateProcessId = [int]$candidate.ParentProcessId
        }
    }
    if (
        $listeners.Count -ne 1 -or
        -not $ownerIsRecordedDescendant
    ) {
        $observedOwners = @($listeners | Select-Object -ExpandProperty OwningProcess) -join ","
        throw (
            "$($ServiceRecord.Name) does not own its expected loopback port " +
            "(expected PID $($ServiceRecord.ServiceProcessId), observed $observedOwners)"
        )
    }
}

function ConvertTo-QuotedArgument {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ($Value.Contains('"')) {
        throw "service argument contains an unsupported quote character"
    }
    return '"{0}"' -f $Value
}

function Start-OwnedService {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("Backend", "Vite")]
        [string]$Service,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$RunDirectory,
        [int]$BackendPort = 0,
        [int]$CorsPort = 0,
        [string]$DataRoot = "",
        [switch]$ServeFrontend,
        [switch]$MigrateDatabase,
        [string]$FrontendDistPath = ""
    )

    if ($Service -eq "Backend" -and [string]::IsNullOrWhiteSpace($DataRoot)) {
        throw "backend E2E service requires an explicit data root"
    }
    if ($Service -eq "Vite" -and -not [string]::IsNullOrWhiteSpace($DataRoot)) {
        throw "Vite E2E service must not receive an application data root"
    }
    Assert-PortAvailable -Port $Port
    $stdoutPath = Join-Path $RunDirectory "$Name.stdout.log"
    $stderrPath = Join-Path $RunDirectory "$Name.stderr.log"
    $manifestPath = Join-Path $RunDirectory "$Name.process.json"
    $arguments = @(
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        (ConvertTo-QuotedArgument -Value $script:ServiceLauncher),
        "-Service",
        $Service,
        "-Port",
        $Port.ToString(),
        "-ProcessManifestPath",
        (ConvertTo-QuotedArgument -Value $manifestPath)
    )
    if ($BackendPort -gt 0) {
        $arguments += @("-BackendPort", $BackendPort.ToString())
    }
    if ($CorsPort -gt 0) {
        $arguments += @("-CorsPort", $CorsPort.ToString())
    }
    if (-not [string]::IsNullOrWhiteSpace($DataRoot)) {
        $arguments += @(
            "-DataRoot",
            (ConvertTo-QuotedArgument -Value $DataRoot)
        )
    }
    if ($ServeFrontend) {
        $arguments += "-ServeFrontend"
        $arguments += @(
            "-FrontendDistPath",
            (ConvertTo-QuotedArgument -Value $FrontendDistPath)
        )
    }
    if ($MigrateDatabase) {
        $arguments += "-MigrateDatabase"
    }

    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $arguments `
        -WorkingDirectory $script:RepositoryRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    $record = [pscustomobject]@{
        Name = $Name
        Port = $Port
        Process = $process
        StartedAt = $process.StartTime.ToUniversalTime()
        ServiceProcessId = 0
        ServiceStartedAt = $null
        StdoutPath = $stdoutPath
        StderrPath = $stderrPath
        ManifestPath = $manifestPath
        DataRoot = $DataRoot
    }
    $script:OwnedProcesses.Add($record)
    $null = $script:OwnedPorts.Add($Port)

    $manifestDeadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $process.Refresh()
        if ($process.HasExited) {
            throw "$Name launcher exited before recording its service process"
        }
        if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
            try {
                $manifest = Get-Content `
                    -LiteralPath $manifestPath `
                    -Raw `
                    -Encoding UTF8 | ConvertFrom-Json
                $serviceProcessId = [int]$manifest.process_id
                $serviceStartedAt = [DateTime]::new(
                    [long]$manifest.started_at_utc_ticks,
                    [DateTimeKind]::Utc
                )
                $serviceProcess = Get-Process `
                    -Id $serviceProcessId `
                    -ErrorAction SilentlyContinue
                if (
                    $null -ne $serviceProcess -and
                    $serviceProcess.StartTime.ToUniversalTime() -eq $serviceStartedAt
                ) {
                    $record.ServiceProcessId = $serviceProcessId
                    $record.ServiceStartedAt = $serviceStartedAt
                    break
                }
            } catch {
                # The launcher may still be completing its atomic-sized manifest write.
            }
        }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $manifestDeadline)

    if ($record.ServiceProcessId -le 0) {
        throw "$Name did not record a valid owned service process"
    }
    return $record
}

function Get-ResponseStatusCode {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest `
            -Uri $Url `
            -Method Get `
            -Headers @{ Accept = "application/json, text/html" } `
            -UseBasicParsing `
            -TimeoutSec 2
        return [int]$response.StatusCode
    } catch {
        $errorResponse = $_.Exception.Response
        if ($null -ne $errorResponse -and $null -ne $errorResponse.StatusCode) {
            return [int]$errorResponse.StatusCode
        }
        return 0
    }
}

function Wait-ServiceUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [int[]]$AcceptedStatusCodes,
        [Parameter(Mandatory = $true)]
        [object]$ServiceRecord,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $ServiceRecord.Process.Refresh()
        if ($ServiceRecord.Process.HasExited) {
            throw "$Name exited before its readiness URL became available"
        }
        $statusCode = Get-ResponseStatusCode -Url $Url
        if ($AcceptedStatusCodes -contains $statusCode) {
            Assert-ServiceOwnsPort -ServiceRecord $ServiceRecord
            return
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "$Name did not become ready before the startup timeout"
}

function Write-LimitedServiceDiagnostics {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RunDirectory
    )

    foreach ($record in $script:OwnedProcesses) {
        foreach ($stream in @(
                @{ Label = "stdout"; Path = $record.StdoutPath },
                @{ Label = "stderr"; Path = $record.StderrPath }
            )) {
            if (-not (Test-Path -LiteralPath $stream.Path -PathType Leaf)) {
                continue
            }
            $lines = @(
                Get-Content `
                    -LiteralPath $stream.Path `
                    -Tail 20 `
                    -Encoding UTF8 `
                    -ErrorAction SilentlyContinue
            )
            if ($lines.Count -eq 0) {
                continue
            }
            [Console]::Error.WriteLine(
                "[e2e] limited $($record.Name) $($stream.Label) diagnostics:"
            )
            foreach ($line in $lines) {
                $sanitized = [string]$line
                foreach ($replacement in @(
                        @($script:RepositoryRoot, "<repository>"),
                        @($script:RepositoryRoot.Replace("\", "/"), "<repository>"),
                        @($RunDirectory, "<e2e-runtime>"),
                        @($RunDirectory.Replace("\", "/"), "<e2e-runtime>")
                    )) {
                    $sanitized = [regex]::Replace(
                        $sanitized,
                        [regex]::Escape($replacement[0]),
                        $replacement[1],
                        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
                    )
                }
                $sanitized = [regex]::Replace(
                    $sanitized,
                    '(https?://[^\s?]+)\?[^\s]+',
                    '$1?<redacted>'
                )
                $sanitized = [regex]::Replace(
                    $sanitized,
                    '(?i)file:///[A-Z]:/[^\s"''<>|]*',
                    'file:///<local-path>'
                )
                $sanitized = [regex]::Replace(
                    $sanitized,
                    '(?i)\b[A-Z]:[\\/][^\s"''<>|]*',
                    '<local-path>'
                )
                $sanitized = [regex]::Replace(
                    $sanitized,
                    '(?i)\\\\[^\s"''<>|]+',
                    '<local-path>'
                )
                $sanitized = [regex]::Replace(
                    $sanitized,
                    '(?i)\b(authorization|cookie|set-cookie|token|api[_-]?key)' +
                    '\s*[:=]\s*[^\s,;]+',
                    '$1=<redacted>'
                )
                $sanitized = [regex]::Replace(
                    $sanitized,
                    ([char]27 + '\[[0-?]*[ -/]*[@-~]'),
                    ''
                )
                if ($sanitized.Length -gt 500) {
                    $sanitized = $sanitized.Substring(0, 500) + "..."
                }
                [Console]::Error.WriteLine("[e2e] $sanitized")
            }
        }
    }
}

function Stop-OwnedServiceTree {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record
    )

    if ($Record.ServiceProcessId -gt 0) {
        $serviceProcess = Get-Process `
            -Id $Record.ServiceProcessId `
            -ErrorAction SilentlyContinue
        if ($null -ne $serviceProcess) {
            if ($serviceProcess.StartTime.ToUniversalTime() -ne $Record.ServiceStartedAt) {
                throw "refusing to stop a reused service process identifier"
            }
            try {
                & taskkill.exe /PID $Record.ServiceProcessId /T /F 2>$null | Out-Null
                $serviceTaskkillExitCode = $LASTEXITCODE
            } catch {
                $serviceTaskkillExitCode = 1
            }
            $serviceProcess.WaitForExit(5000) | Out-Null
            $serviceProcess.Refresh()
            if (-not $serviceProcess.HasExited) {
                throw (
                    "failed to stop owned service process: $($Record.Name) " +
                    "(taskkill exit code $serviceTaskkillExitCode)"
                )
            }
        }
    }

    $Record.Process.Refresh()
    if ($Record.Process.HasExited) {
        return
    }
    $currentProcess = Get-Process -Id $Record.Process.Id -ErrorAction SilentlyContinue
    if ($null -eq $currentProcess) {
        return
    }
    $currentStartedAt = $currentProcess.StartTime.ToUniversalTime()
    if ($currentStartedAt -ne $Record.StartedAt) {
        throw "refusing to stop a reused process identifier"
    }

    try {
        & taskkill.exe /PID $Record.Process.Id /T /F 2>$null | Out-Null
        $taskkillExitCode = $LASTEXITCODE
    } catch {
        $taskkillExitCode = 1
    }
    $Record.Process.WaitForExit(5000) | Out-Null
    $Record.Process.Refresh()
    if (-not $Record.Process.HasExited) {
        throw (
            "failed to stop owned service tree: $($Record.Name) " +
            "(taskkill exit code $taskkillExitCode)"
        )
    }
}

function Remove-ValidatedRunDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RunDirectory
    )

    Assert-E2ERunDirectoryIdentity -RunDirectory $RunDirectory
    Assert-SafeContainedPath `
        -Candidate $RunDirectory `
        -Container $script:RepositoryRoot `
        -Description "E2E run directory"
    Assert-SafeContainedPath `
        -Candidate $RunDirectory `
        -Container $script:RuntimeRoot `
        -Description "E2E run directory"
    $fullRunDirectory = [System.IO.Path]::GetFullPath($RunDirectory)
    if (Test-Path -LiteralPath $fullRunDirectory) {
        Assert-NoReparsePointsInTree `
            -Root $fullRunDirectory `
            -Description "E2E run directory"
        Remove-Item -LiteralPath $fullRunDirectory -Recurse -Force
    }
    if (Test-Path -LiteralPath $fullRunDirectory) {
        throw "E2E run directory still exists after controlled cleanup"
    }
    if (Test-Path -LiteralPath $script:RuntimeRoot -PathType Container) {
        $runtimeRootItem = Get-Item -LiteralPath $script:RuntimeRoot -Force
        if (
            ($runtimeRootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            throw "E2E runtime root must not be a reparse point"
        }
        $remaining = @(Get-ChildItem -LiteralPath $script:RuntimeRoot -Force)
        if ($remaining.Count -eq 0) {
            Remove-Item -LiteralPath $script:RuntimeRoot -Force
        }
    }
}

function Remove-SuccessArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("development", "integrated")]
        [string]$ModeName
    )

    foreach ($relativePath in @(
            "playwright-results/$ModeName",
            "playwright-report/$ModeName"
        )) {
        $candidate = Join-Path $script:FrontendRoot $relativePath
        $fullCandidate = [System.IO.Path]::GetFullPath($candidate)
        $frontendPrefix = (
            [System.IO.Path]::GetFullPath($script:FrontendRoot).TrimEnd("\", "/") +
            [System.IO.Path]::DirectorySeparatorChar
        )
        if (-not $fullCandidate.StartsWith(
                $frontendPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
            throw "refusing to remove Playwright artifacts outside frontend"
        }
        Assert-SafeContainedPath `
            -Candidate $fullCandidate `
            -Container $script:FrontendRoot `
            -Description "Playwright artifact directory"
        if (Test-Path -LiteralPath $fullCandidate) {
            Assert-NoReparsePointsInTree `
                -Root $fullCandidate `
                -Description "Playwright artifact directory"
            Remove-Item -LiteralPath $fullCandidate -Recurse -Force
        }
    }
    foreach ($relativeParent in @("playwright-results", "playwright-report")) {
        $parentPath = Join-Path $script:FrontendRoot $relativeParent
        Assert-SafeContainedPath `
            -Candidate $parentPath `
            -Container $script:FrontendRoot `
            -Description "Playwright artifact root"
        if (
            (Test-Path -LiteralPath $parentPath -PathType Container) -and
            @(Get-ChildItem -LiteralPath $parentPath -Force).Count -eq 0
        ) {
            Remove-Item -LiteralPath $parentPath -Force
        }
    }
}

function Invoke-Playwright {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigFile,
        [Parameter(Mandatory = $true)]
        [hashtable]$Environment,
        [string[]]$TestPaths = @(),
        [string]$GrepPattern = ""
    )

    $Environment["NODE_PATH"] = Join-Path $script:FrontendRoot "node_modules"
    $previousValues = @{}
    foreach ($name in $Environment.Keys) {
        $previousValues[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $Environment[$name], "Process")
    }

    try {
        Push-Location $script:FrontendRoot
        try {
            $arguments = @("test", "--config=$ConfigFile") + $TestPaths
            if (-not [string]::IsNullOrWhiteSpace($GrepPattern)) {
                $arguments += "--grep=$GrepPattern"
            }
            if ($Headed) {
                $arguments += "--headed"
            }
            & $script:PlaywrightExecutable @arguments | Out-Host
            $playwrightExitCode = $LASTEXITCODE
            return [int]$playwrightExitCode
        } finally {
            Pop-Location
        }
    } finally {
        foreach ($name in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable(
                $name,
                $previousValues[$name],
                "Process"
            )
        }
    }
}

function Assert-ChromiumInstalled {
    if (-not (Test-Path -LiteralPath $script:PlaywrightExecutable -PathType Leaf)) {
        throw "Playwright is not installed in frontend/node_modules"
    }

    Push-Location $script:FrontendRoot
    try {
        & node -e (
            "const fs=require('node:fs');" +
            "const {chromium}=require('@playwright/test');" +
            "process.exit(fs.existsSync(chromium.executablePath())?0:1);"
        )
        $probeExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($probeExitCode -ne 0) {
        throw "Playwright Chromium is missing; run 'Set-Location frontend; npm run e2e:install'"
    }
}

function Assert-E2EEnvironment {
    foreach ($command in @(
            "git",
            "node",
            "npm.cmd",
            "powershell.exe",
            "taskkill.exe"
        )) {
        if ($null -eq (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "required E2E command is unavailable: $command"
        }
    }

    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
        throw "root virtual environment is missing"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $script:FrontendRoot "node_modules") -PathType Container)) {
        throw "frontend dependencies are missing"
    }

    $gitRootOutput = & git -C $script:RepositoryRoot rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "repository root is not a Git work tree"
    }
    $gitRoot = [System.IO.Path]::GetFullPath(
        ($gitRootOutput | Select-Object -First 1)
    )
    if (-not $gitRoot.TrimEnd("\", "/").Equals(
            $script:RepositoryRoot.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "E2E runner resolved an unexpected Git repository"
    }

    & $pythonExecutable -c (
        "import struct, sys; " +
        "raise SystemExit(0 if sys.version_info[:3] == (3, 12, 10) " +
        "and struct.calcsize('P') * 8 == 64 else 1)"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "E2E requires 64-bit Python 3.12.10 in the root virtual environment"
    }

    & node -e (
        "const major=Number(process.versions.node.split('.')[0]);" +
        "process.exit(major===24 && process.arch==='x64' ? 0 : 1);"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "E2E requires 64-bit Node.js major version 24"
    }
}

function Invoke-FrontendBuild {
    $previousApiBaseUrl = [Environment]::GetEnvironmentVariable(
        "VITE_API_BASE_URL",
        "Process"
    )
    try {
        [Environment]::SetEnvironmentVariable(
            "VITE_API_BASE_URL",
            "/api/v1",
            "Process"
        )
        Push-Location $script:FrontendRoot
        try {
            & npm.cmd run build
            $buildExitCode = $LASTEXITCODE
        } finally {
            Pop-Location
        }
    } finally {
        [Environment]::SetEnvironmentVariable(
            "VITE_API_BASE_URL",
            $previousApiBaseUrl,
            "Process"
        )
    }
    if ($buildExitCode -ne 0) {
        throw "frontend production build failed with exit code $buildExitCode"
    }
}

function Invoke-E2EScenario {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet(
            "E2E-DEV-001",
            "E2E-DEV-002",
            "E2E-DEV-003",
            "E2E-INT-001",
            "E2E-INT-002",
            "E2E-INT-003",
            "E2E-INT-004",
            "E2E-INT-005",
            "E2E-INT-006",
            "E2E-INT-007",
            "E2E-INT-008",
            "E2E-INT-009",
            "E2E-INT-010",
            "E2E-INT-011",
            "E2E-INT-012",
            "E2E-INT-013",
            "E2E-INT-014",
            "E2E-INT-015",
            "E2E-INT-016",
            "E2E-INT-017",
            "E2E-STARTUP-001"
        )]
        [string]$SelectedScenario
    )

    $script:OwnedProcesses = [System.Collections.Generic.List[object]]::new()
    $script:OwnedPorts = [System.Collections.Generic.HashSet[int]]::new()
    $isDevelopment = $SelectedScenario.StartsWith(
        "E2E-DEV-",
        [System.StringComparison]::Ordinal
    )
    $isMissingBuild = $SelectedScenario -eq "E2E-STARTUP-001"
    $isBusinessApi = $SelectedScenario -in @(
        "E2E-INT-006",
        "E2E-INT-007",
        "E2E-INT-008",
        "E2E-INT-009",
        "E2E-INT-010",
        "E2E-INT-011",
        "E2E-INT-012",
        "E2E-INT-013",
        "E2E-INT-014",
        "E2E-INT-015",
        "E2E-INT-016",
        "E2E-INT-017"
    )
    $modeName = if ($isDevelopment) { "development" } else { "integrated" }
    $scenarioName = $SelectedScenario.ToLowerInvariant()
    $runToken = [guid]::NewGuid().ToString("N")
    $runId = "{0}-{1}-{2}" -f $scenarioName, $PID, $runToken
    $runDirectory = Join-Path $script:RuntimeRoot $runId
    $dataRoot = Join-Path $runDirectory "AIWebNovel-E2E-DataRoot-$runToken"
    Assert-E2ERunDirectoryIdentity -RunDirectory $runDirectory
    Assert-SafeContainedPath `
        -Candidate $runDirectory `
        -Container $script:RepositoryRoot `
        -Description "E2E run directory"
    Assert-SafeContainedPath `
        -Candidate $runDirectory `
        -Container $script:RuntimeRoot `
        -Description "E2E run directory"
    Assert-E2EDataRootIdentity -DataRoot $dataRoot -RunDirectory $runDirectory
    foreach ($artifactPath in @(
            (Join-Path $script:FrontendRoot "playwright-results/$modeName"),
            (Join-Path $script:FrontendRoot "playwright-report/$modeName")
        )) {
        Assert-SafeContainedPath `
            -Candidate $artifactPath `
            -Container $script:FrontendRoot `
            -Description "Playwright artifact directory"
    }
    $runSucceeded = $false
    $runFailure = $null
    $cleanupFailure = $null
    try {
        New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
        if (Test-Path -LiteralPath $dataRoot) {
            throw "E2E data root must not exist before backend storage initialization"
        }
        if ($isDevelopment) {
            $backendPort = 18120
            $vitePort = 14173
            $selectedProxyPort = if ($ProxyBackendPort -gt 0) {
                $ProxyBackendPort
            } else {
                $backendPort
            }
            if ($selectedProxyPort -ne $backendPort) {
                Assert-PortAvailable -Port $selectedProxyPort
            }

            $backend = Start-OwnedService `
                -Service Backend `
                -Name "development-backend" `
                -Port $backendPort `
                -RunDirectory $runDirectory `
                -DataRoot $dataRoot `
                -CorsPort $vitePort
            Wait-ServiceUrl `
                -Name "development backend" `
                -Url "http://127.0.0.1:$backendPort/api/v1/health/ready" `
                -AcceptedStatusCodes @(200) `
                -ServiceRecord $backend
            Assert-E2EStorageLayout `
                -DataRoot $dataRoot `
                -RunDirectory $runDirectory `
                -ScenarioName $scenarioName

            $vite = Start-OwnedService `
                -Service Vite `
                -Name "development-vite" `
                -Port $vitePort `
                -RunDirectory $runDirectory `
                -BackendPort $selectedProxyPort
            Wait-ServiceUrl `
                -Name "development Vite" `
                -Url "http://127.0.0.1:$vitePort/" `
                -AcceptedStatusCodes @(200) `
                -ServiceRecord $vite

            if ($SimulateStartupInterruption) {
                throw "controlled startup interruption requested"
            }

            $playwrightExitCode = Invoke-Playwright `
                -ConfigFile "playwright.dev.config.ts" `
                -Environment @{
                    AIWEBNOVEL_E2E_BASE_URL = "http://127.0.0.1:$vitePort"
                    AIWEBNOVEL_E2E_BACKEND_URL = "http://127.0.0.1:$backendPort"
                } `
                -TestPaths @("../tests/e2e/development") `
                -GrepPattern "^$SelectedScenario"
        } elseif ($isMissingBuild) {
            $missingBuildPort = 18122
            $missingBuildDist = Join-Path $runDirectory "missing-build-dist"
            New-Item -ItemType Directory -Path $missingBuildDist -Force | Out-Null

            $missingBuild = Start-OwnedService `
                -Service Backend `
                -Name "missing-build-backend" `
                -Port $missingBuildPort `
                -RunDirectory $runDirectory `
                -DataRoot $dataRoot `
                -ServeFrontend `
                -FrontendDistPath $missingBuildDist
            Wait-ServiceUrl `
                -Name "missing-build live endpoint" `
                -Url "http://127.0.0.1:$missingBuildPort/api/v1/health/live" `
                -AcceptedStatusCodes @(200) `
                -ServiceRecord $missingBuild
            Wait-ServiceUrl `
                -Name "missing-build readiness endpoint" `
                -Url "http://127.0.0.1:$missingBuildPort/api/v1/health/ready" `
                -AcceptedStatusCodes @(503) `
                -ServiceRecord $missingBuild
            Assert-E2EStorageLayout `
                -DataRoot $dataRoot `
                -RunDirectory $runDirectory `
                -ScenarioName $scenarioName
            Wait-ServiceUrl `
                -Name "missing-build root endpoint" `
                -Url "http://127.0.0.1:$missingBuildPort/" `
                -AcceptedStatusCodes @(503) `
                -ServiceRecord $missingBuild

            if ($SimulateStartupInterruption) {
                throw "controlled startup interruption requested"
            }

            $playwrightExitCode = Invoke-Playwright `
                -ConfigFile "playwright.integrated.config.ts" `
                -Environment @{
                    AIWEBNOVEL_E2E_BASE_URL = "http://127.0.0.1:$missingBuildPort"
                    AIWEBNOVEL_E2E_BACKEND_URL = "http://127.0.0.1:$missingBuildPort"
                    AIWEBNOVEL_E2E_MISSING_BUILD_BASE_URL = (
                        "http://127.0.0.1:$missingBuildPort"
                    )
                } `
                -TestPaths @("../tests/e2e/startup-failure") `
                -GrepPattern "^$SelectedScenario"
        } else {
            $integratedPort = 18121
            $frontendDist = Join-Path $script:FrontendRoot "dist"

            $integrated = Start-OwnedService `
                -Service Backend `
                -Name "integrated-backend" `
                -Port $integratedPort `
                -RunDirectory $runDirectory `
                -DataRoot $dataRoot `
                -ServeFrontend `
                -MigrateDatabase:$isBusinessApi `
                -FrontendDistPath $frontendDist
            Wait-ServiceUrl `
                -Name "integrated backend" `
                -Url "http://127.0.0.1:$integratedPort/api/v1/health/ready" `
                -AcceptedStatusCodes @(200) `
                -ServiceRecord $integrated
            Assert-E2EStorageLayout `
                -DataRoot $dataRoot `
                -RunDirectory $runDirectory `
                -ScenarioName $scenarioName
            Wait-ServiceUrl `
                -Name "integrated frontend" `
                -Url "http://127.0.0.1:$integratedPort/" `
                -AcceptedStatusCodes @(200) `
                -ServiceRecord $integrated

            if ($SimulateStartupInterruption) {
                throw "controlled startup interruption requested"
            }

            $playwrightExitCode = Invoke-Playwright `
                -ConfigFile "playwright.integrated.config.ts" `
                -Environment @{
                    AIWEBNOVEL_E2E_BASE_URL = "http://127.0.0.1:$integratedPort"
                    AIWEBNOVEL_E2E_BACKEND_URL = "http://127.0.0.1:$integratedPort"
                } `
                -TestPaths @("../tests/e2e/integrated") `
                -GrepPattern "^$SelectedScenario"
        }

        if ($playwrightExitCode -ne 0) {
            throw "Playwright $modeName tests failed with exit code $playwrightExitCode"
        }
        if ($SelectedScenario -eq "E2E-INT-008") {
            Assert-ProjectFrontendDatabaseCounts -DataRoot $dataRoot
        }
        if ($SelectedScenario -eq "E2E-INT-009") {
            Assert-ProjectDetailDatabaseState -DataRoot $dataRoot
        }
        if ($SelectedScenario -eq "E2E-INT-010") {
            Assert-ProjectRevisionHistoryDatabaseState -DataRoot $dataRoot
        }
        if ($SelectedScenario -eq "E2E-INT-011") {
            Assert-StoryBibleHttpDatabaseState -DataRoot $dataRoot
        }
        if ($SelectedScenario -eq "E2E-INT-012") {
            Assert-StoryBibleFrontendDatabaseState -DataRoot $dataRoot
        }
        if ($SelectedScenario -eq "E2E-INT-013") {
            Assert-StoryBibleRevisionHistoryDatabaseState -DataRoot $dataRoot
        }
        if ($SelectedScenario -eq "E2E-INT-014") {
            Assert-CharacterHttpDatabaseState -DataRoot $dataRoot
        }
        if ($SelectedScenario -eq "E2E-INT-015") {
            Assert-CharacterFrontendDatabaseState -DataRoot $dataRoot
        }
        if ($SelectedScenario -eq "E2E-INT-016") {
            Assert-CharacterRevisionHistoryDatabaseState -DataRoot $dataRoot
        }
        if ($isBusinessApi) {
            foreach ($logPath in Get-ChildItem -LiteralPath $runDirectory -Filter "*.log") {
                $logText = Get-Content -LiteralPath $logPath.FullName -Raw -Encoding UTF8
                if (
                    $logText -match "E2E-PROJECT-(?:TITLE|DESCRIPTION)-CANARY-006" -or
                    $logText -match "E2E-PROJECT-LIST-BODY-CANARY-007" -or
                    $logText -match "E2E_PROJECT_LIST_CURSOR_CANARY_007" -or
                    $logText -match "E2E-PROJECT-FRONTEND-DESCRIPTION-CANARY-008" -or
                    $logText -match "E2E-PROJECT-(?:DETAIL|CONFLICT)-.+-CANARY-009" -or
                    $logText -match "E2E-PROJECT-HISTORY-DESCRIPTION-CANARY-010" -or
                    $logText -match "E2E-STORY-BIBLE-(?:TITLE|CONTENT)-CANARY-011" -or
                    $logText -match "E2E-STORY-BIBLE-(?:PROJECT-DESCRIPTION|UI-CONTENT)-CANARY-012" -or
                    $logText -match "E2E-STORY-BIBLE-HISTORY-(?:PROJECT|CONTENT)-CANARY-013" -or
                    $logText -match "E2E-CHARACTER-PROFILE-CANARY-014" -or
                    $logText -match "E2E-CHARACTER-PROFILE-CANARY-015" -or
                    $logText -match "E2E-CHARACTER-HISTORY-PROFILE-CANARY-016" -or
                    $logText -match "E2E-NOVEL-STRUCTURE-.+-CANARY-017" -or
                    $logText -match "(?i)\bcursor=" -or
                    $logText -match "If-Match"
                ) {
                    throw "Business API private request content appeared in service logs"
                }
            }
        }
        $runSucceeded = $true
    } catch {
        $runFailure = $_.Exception.Message
        Write-LimitedServiceDiagnostics -RunDirectory $runDirectory
    } finally {
        $cleanupIssues = [System.Collections.Generic.List[string]]::new()
        $processesToStop = $script:OwnedProcesses.ToArray()
        [array]::Reverse($processesToStop)
        foreach ($record in $processesToStop) {
            try {
                Stop-OwnedServiceTree -Record $record
            } catch {
                $cleanupIssues.Add($_.Exception.Message)
            }
        }
        foreach ($port in $script:OwnedPorts) {
            try {
                Wait-PortReleased -Port $port
            } catch {
                $cleanupIssues.Add($_.Exception.Message)
            }
        }
        if ($cleanupIssues.Count -eq 0) {
            try {
                Remove-ValidatedRunDirectory -RunDirectory $runDirectory
                if ($runSucceeded) {
                    Remove-SuccessArtifacts -ModeName $modeName
                }
            } catch {
                $cleanupIssues.Add($_.Exception.Message)
            }
        }
        if ($cleanupIssues.Count -gt 0) {
            $cleanupFailure = $cleanupIssues -join "; "
        }
    }

    if ($null -ne $cleanupFailure) {
        throw "E2E cleanup failed: $cleanupFailure"
    }
    if ($null -ne $runFailure) {
        throw $runFailure
    }
}

$currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
$allowedDirectories = @(
    $script:RepositoryRoot.TrimEnd("\", "/"),
    $script:FrontendRoot.TrimEnd("\", "/")
)
if (-not ($allowedDirectories -contains $currentDirectory.TrimEnd("\", "/"))) {
    [Console]::Error.WriteLine(
        "[e2e] run from the repository root or through the frontend package scripts"
    )
    exit 1
}
if (-not (Test-Path -LiteralPath $script:ServiceLauncher -PathType Leaf)) {
    [Console]::Error.WriteLine("[e2e] service launcher is missing")
    exit 1
}
if ($Mode -ne "Development" -and $ProxyBackendPort -gt 0) {
    [Console]::Error.WriteLine("[e2e] ProxyBackendPort is limited to Development mode")
    exit 1
}
if ($Mode -eq "All" -and $SimulateStartupInterruption -and [string]::IsNullOrWhiteSpace($Scenario)) {
    [Console]::Error.WriteLine(
        "[e2e] SimulateStartupInterruption requires one explicit mode"
    )
    exit 1
}

try {
    Assert-E2EEnvironment
    Assert-ChromiumInstalled
    $scenarioModes = @{
        "E2E-DEV-001" = "Development"
        "E2E-DEV-002" = "Development"
        "E2E-DEV-003" = "Development"
        "E2E-INT-001" = "Integrated"
        "E2E-INT-002" = "Integrated"
        "E2E-INT-003" = "Integrated"
        "E2E-INT-004" = "Integrated"
        "E2E-INT-005" = "Integrated"
        "E2E-INT-006" = "Integrated"
        "E2E-INT-007" = "Integrated"
        "E2E-INT-008" = "Integrated"
        "E2E-INT-009" = "Integrated"
        "E2E-INT-010" = "Integrated"
        "E2E-INT-011" = "Integrated"
        "E2E-INT-012" = "Integrated"
        "E2E-INT-013" = "Integrated"
        "E2E-INT-014" = "Integrated"
        "E2E-INT-015" = "Integrated"
        "E2E-INT-016" = "Integrated"
        "E2E-INT-017" = "Integrated"
        "E2E-STARTUP-001" = "Integrated"
    }
    $developmentScenarios = @("E2E-DEV-001", "E2E-DEV-002", "E2E-DEV-003")
    $integratedScenarios = @(
        "E2E-INT-001",
        "E2E-INT-002",
        "E2E-INT-003",
        "E2E-INT-004",
        "E2E-INT-005",
        "E2E-INT-006",
        "E2E-INT-007",
        "E2E-INT-008",
        "E2E-INT-009",
        "E2E-INT-010",
        "E2E-INT-011",
        "E2E-INT-012",
        "E2E-INT-013",
        "E2E-INT-014",
        "E2E-INT-015",
        "E2E-INT-016",
        "E2E-INT-017",
        "E2E-STARTUP-001"
    )

    if (-not [string]::IsNullOrWhiteSpace($Scenario)) {
        if (-not $scenarioModes.ContainsKey($Scenario)) {
            throw "unknown E2E scenario: $Scenario"
        }
        $scenarioMode = $scenarioModes[$Scenario]
        if ($Mode -ne "All" -and $Mode -ne $scenarioMode) {
            throw "scenario $Scenario does not belong to $Mode mode"
        }
        $selectedScenarios = @($Scenario)
    } elseif ($Mode -eq "Development") {
        $selectedScenarios = $developmentScenarios
    } elseif ($Mode -eq "Integrated") {
        $selectedScenarios = $integratedScenarios
    } else {
        $selectedScenarios = $developmentScenarios + $integratedScenarios
    }

    $needsProductionBuild = @(
        $selectedScenarios | Where-Object { $_ -like "E2E-INT-*" }
    ).Count -gt 0
    if ($needsProductionBuild) {
        Invoke-FrontendBuild
    }

    foreach ($selectedScenario in $selectedScenarios) {
        Write-Host "[e2e] running $selectedScenario"
        Invoke-E2EScenario -SelectedScenario $selectedScenario
        Write-Host "[e2e] passed $selectedScenario"
    }
    Write-Host "[e2e] all requested browser acceptance tests passed"
    exit 0
} catch {
    [Console]::Error.WriteLine("[e2e] failed: $($_.Exception.Message)")
    exit 1
}

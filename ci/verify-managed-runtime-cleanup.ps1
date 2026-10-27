# Safe temporary-directory regression tests for the two Control Plane installers.
# Never invoke the real installer, network, pip, or actual LOCALAPPDATA contents.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$installers = @(
    (Join-Path $repositoryRoot 'scripts\install.ps1'),
    (Join-Path $repositoryRoot 'Packages\com.darumappap.unity-agent\Editor\Bootstrap~\install-control-plane.ps1')
)

$script:RunningPaths = @()
$script:ProcessInventoryBlocked = $false
function Get-CimInstance {
    param([string]$ClassName, [string]$Filter)
    if ($script:ProcessInventoryBlocked) {
        throw "Simulated process enumeration failure"
    }
    foreach ($runningPath in $script:RunningPaths) {
        [pscustomobject]@{ ExecutablePath = $runningPath }
    }
}

function New-MockManagedRuntime {
    param([string]$Root, [string]$Tag, [switch]$Incomplete)
    $runtime = Join-Path $Root $Tag
    $venv = Join-Path $runtime 'venv'
    $scripts = Join-Path $venv 'Scripts'
    New-Item -ItemType Directory -Path $scripts -Force | Out-Null
    if (-not $Incomplete) {
        Set-Content -LiteralPath (Join-Path $venv 'pyvenv.cfg') -Value 'home = testing'
        Set-Content -LiteralPath (Join-Path $scripts 'unity-agent.exe') -Value 'test fixture only'
    }
    return $runtime
}

function Assert-True {
    param([bool]$Condition, [string]$Description)
    if (-not $Condition) {
        throw "FAILED: $Description"
    }
}

$expectedBody = $null
foreach ($installer in $installers) {
    $tokens = $null
    $parseErrors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($installer,
        [ref]$tokens, [ref]$parseErrors)
    Assert-True ($parseErrors.Count -eq 0) "PowerShell syntax for $installer"

    $fn = @($ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Remove-OldManagedControlPlanes'
    }, $true))
    Assert-True ($fn.Count -eq 1) "cleanup function occurs once in $installer"
    $source = $fn[0].Extent.Text
    if ($null -ne $expectedBody) {
        Assert-True ($source -ceq $expectedBody) "Both installer cleanup functions must be identical"
    } else {
        $expectedBody = $source
    }

    Invoke-Expression $source

    $sandbox = Join-Path ([IO.Path]::GetTempPath()) ('UnityAgent-cleanup-test-' + [guid]::NewGuid().ToString('N'))
    $root = Join-Path $sandbox 'UnityAgent\ControlPlane'
    try {
        New-Item -ItemType Directory -Path $root -Force | Out-Null
        $old = New-MockManagedRuntime -Root $root -Tag 'v0.0.6-beta'
        $same = New-MockManagedRuntime -Root $root -Tag 'v0.0.8-beta'
        $newer = New-MockManagedRuntime -Root $root -Tag 'v0.0.9-beta'
        $prereleaseOld = New-MockManagedRuntime -Root $root -Tag 'v0.0.8-alpha'
        $unrecognized = New-MockManagedRuntime -Root $root -Tag 'developer-workspace'
        $incomplete = New-MockManagedRuntime -Root $root -Tag 'v0.0.5-beta' -Incomplete

        $script:RunningPaths = @((Join-Path $old 'venv\Scripts\unity-agent.exe'))
        Remove-OldManagedControlPlanes -ManagedRoot $root -ActiveTag 'v0.0.8-beta'
        Assert-True (Test-Path -LiteralPath $old) "Keep running older runtime"
        Assert-True (-not (Test-Path -LiteralPath $prereleaseOld)) "Remove older prerelease"
        Assert-True (Test-Path -LiteralPath $same) "Keep currently active version"
        Assert-True (Test-Path -LiteralPath $newer) "Never delete newer version"
        Assert-True (Test-Path -LiteralPath $unrecognized) "Keep unrelated directories"
        Assert-True (Test-Path -LiteralPath $incomplete) "Keep unrecognized incomplete venv"

        $script:ProcessInventoryBlocked = $true
        $script:RunningPaths = @()
        Remove-OldManagedControlPlanes -ManagedRoot $root -ActiveTag 'v0.0.8-beta'
        Assert-True (Test-Path -LiteralPath $old) "No deletes if process inventory is unavailable"

        $script:ProcessInventoryBlocked = $false
        Remove-OldManagedControlPlanes -ManagedRoot $root -ActiveTag 'v0.0.8-beta'
        Assert-True (-not (Test-Path -LiteralPath $old)) "Remove obsolete runtime after use ends"
        Assert-True (Test-Path -LiteralPath $same) "Keep active runtime after cleanup"
        Assert-True (Test-Path -LiteralPath $newer) "Keep newer runtime after cleanup"
        Assert-True (Test-Path -LiteralPath $incomplete) "Keep unverified runtime after cleanup"

        Write-Host "PASS managed cleanup: $([IO.Path]::GetFileName($installer))"
    }
    finally {
        $script:RunningPaths = @()
        $script:ProcessInventoryBlocked = $false
        Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Windows PowerShell 5.1 / PowerShell 7. Exit codes: 0 PASS, 1 FAIL, 2 BLOCKED_NOT_RUN.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Fixture,
    [string]$OutputDirectory,
    [string]$EditorPath,
    [string]$EditorRoot,
    [string]$PythonCommand,
    [ValidateRange(1, 2147483647)]
    [int]$TimeoutSeconds = 3600,
    [switch]$Canary
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runner = Join-Path $repositoryRoot 'ci/verify/unity_ci.py'
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $repositoryRoot "artifacts/$Fixture"
}
# Relative output is relative to the caller, independent of the script location.
$OutputDirectory = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
$pythonArguments = @()
if (-not $PythonCommand) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonCommand = 'py'
        $pythonArguments += '-3'
    } else {
        $PythonCommand = 'python'
    }
}
if (-not (Get-Command $PythonCommand -ErrorAction SilentlyContinue)) {
    Write-Error 'Python 3.12+ is required. Install it separately or pass -PythonCommand.' -ErrorAction Continue
    exit 2
}
$pythonArguments += @($runner, '--fixture', $Fixture, '--output', $OutputDirectory,
                      '--timeout', [string]$TimeoutSeconds)
if ($EditorPath) { $pythonArguments += @('--editor', $EditorPath) }
if ($EditorRoot) { $pythonArguments += @('--editor-root', $EditorRoot) }
if ($Canary) { $pythonArguments += '--canary' }
# Native nonzero exits are data, not a PowerShell exception. Preserve Python's code.
$PSNativeCommandUseErrorActionPreference = $false
& $PythonCommand @pythonArguments
exit $LASTEXITCODE

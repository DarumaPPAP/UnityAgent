[CmdletBinding()]
param(
    [string]$ProjectPath = $env:UNITY_ARTIST_PROJECT_PATH,
    [string]$HostPath = $env:UNITY_ARTIST_CLI_PATH,
    [switch]$SkipEditorInspect,
    [string]$TranscriptPath = (Join-Path ([System.IO.Path]::GetTempPath()) ("unity-artist-external-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt"))
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$hadFailure = $false

function Resolve-HostExecutable {
    if (-not [string]::IsNullOrWhiteSpace($HostPath)) {
        return (Resolve-Path -LiteralPath $HostPath -ErrorAction Stop).Path
    }

    $pathCommand = Get-Command unity-artist -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $pathCommand) {
        return $pathCommand.Source
    }

    $candidates = @(
        (Join-Path $repoRoot "cli\artist\bin\Release\net8.0\unity-artist.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw "unity-artist was not found on PATH or in the local build output. Build it first or pass -HostPath."
}

function Invoke-ExternalCheck {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    Write-Host "`n>>> $Label"
    & $Executable @Arguments
    $exitCode = $LASTEXITCODE
    Write-Host "exitCode=$exitCode"
    if ($exitCode -ne 0) {
        $script:hadFailure = $true
    }
}

$hostExecutable = Resolve-HostExecutable
$hostDirectory = Split-Path -Parent $hostExecutable
$pathSeparator = [System.IO.Path]::PathSeparator
$pathParts = @($env:Path -split [regex]::Escape([string]$pathSeparator))
if ($pathParts -notcontains $hostDirectory) {
    $env:Path = "$hostDirectory$pathSeparator$env:Path"
}

$unityCommand = Get-Command unity -CommandType Application -ErrorAction Stop
$unityExecutable = $unityCommand.Source
$unityArtistCommand = Get-Command unity-artist -CommandType Application -ErrorAction Stop

$project = $null
if (-not $SkipEditorInspect) {
    $projectInput = if ([string]::IsNullOrWhiteSpace($ProjectPath)) { (Get-Location).Path } else { $ProjectPath }
    $project = (Resolve-Path -LiteralPath $projectInput -ErrorAction Stop).Path
    $projectVersion = Join-Path $project "ProjectSettings\ProjectVersion.txt"
    if (-not (Test-Path -LiteralPath $projectVersion -PathType Leaf)) {
        throw "ProjectPath must point to a Unity project containing ProjectSettings/ProjectVersion.txt. Use -ProjectPath . from the project root."
    }
}

Start-Transcript -LiteralPath $TranscriptPath -Force | Out-Null
try {
    Write-Host "UnityArtistCLI external verification"
    Write-Host "hostExecutable=unity-artist (resolved from PATH/local artifact)"
    Write-Host "projectPathArgument=. (resolved internally; machine-specific paths are not part of the command contract)"

    Invoke-ExternalCheck "unity --version" $unityExecutable @("--version")
    Invoke-ExternalCheck "unity-artist --help" $unityArtistCommand.Source @("--help", "--format", "json", "--non-interactive")
    Invoke-ExternalCheck "unity artist help" $unityExecutable @("artist", "help", "--format", "json", "--non-interactive", "--no-banner")
    Invoke-ExternalCheck "unity artist version" $unityExecutable @("artist", "version", "--format", "json", "--non-interactive", "--no-banner")

    if (-not $SkipEditorInspect) {
        Push-Location $project
        try {
            Invoke-ExternalCheck "unity list --project-path ." $unityExecutable @("list", "--project-path", ".", "--format", "json", "--non-interactive", "--no-banner")
            Invoke-ExternalCheck "unity artist inspect --project-path ." $unityExecutable @("artist", "inspect", "--project-path", ".", "--format", "json", "--non-interactive", "--no-banner")
        }
        finally {
            Pop-Location
        }
    }
}
finally {
    Stop-Transcript | Out-Null
}

Write-Host "Transcript: $TranscriptPath"
if ($hadFailure) {
    exit 1
}
exit 0

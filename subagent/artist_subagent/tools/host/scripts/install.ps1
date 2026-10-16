[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "UnityArtistCLI\Beta"),
    [switch]$AddToUserPath
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$project = Join-Path $repoRoot "cli\artist\UnityArtist.Cli.csproj"

dotnet publish $project --configuration Release --self-contained false --output $InstallRoot

if ($AddToUserPath) {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($currentPath -split ";" | Where-Object { $_ })
    if ($parts -notcontains $InstallRoot) {
        [Environment]::SetEnvironmentVariable("Path", (($parts + $InstallRoot) -join ";"), "User")
    }
}

Write-Host "Installed unity-artist to $InstallRoot"
Write-Host "Verify with: unity-artist version --format json --non-interactive"

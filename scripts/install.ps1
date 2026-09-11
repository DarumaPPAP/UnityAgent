# UnityAgent stable bootstrap installer for Windows PowerShell.
#
# Recommended usage:
#   irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1 | iex
#
# The bootstrap URL stays on main, while the installed Control Plane comes from a
# published GitHub Release and is verified against that release's SHA256SUMS.txt.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

if ($PSVersionTable.PSVersion.Major -lt 5) {
    throw "PowerShell 5.1 or newer is required."
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repository = "DarumaPPAP/UnityAgent"
$releaseTag = if ($env:UNITY_AGENT_TAG) { $env:UNITY_AGENT_TAG.Trim() } else { "v0.0.1-beta" }

if ([string]::IsNullOrWhiteSpace($releaseTag) -or $releaseTag -notmatch '^v[A-Za-z0-9._-]+$') {
    throw "UNITY_AGENT_TAG must be a release tag such as v0.0.1-beta."
}

function Resolve-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{
            Command = $py.Source
            Prefix = @("-3")
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            Command = $python.Source
            Prefix = @()
        }
    }

    throw "Python 3.10 or newer was not found. Install Python, then rerun the installer."
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Python,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Python.Command @($Python.Prefix + $Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
}

$python = Resolve-Python

& $python.Command @($python.Prefix + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"))
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.10 or newer is required."
}

Invoke-Python -Python $python -Arguments @("-m", "pip", "--version")

$releaseApi = "https://api.github.com/repos/$repository/releases/tags/$releaseTag"
$headers = @{
    "User-Agent" = "UnityAgent-Installer"
    "Accept" = "application/vnd.github+json"
}

Write-Host "Resolving UnityAgent release $releaseTag..."
$release = Invoke-RestMethod -Uri $releaseApi -Headers $headers -UseBasicParsing
if ($release.draft) {
    throw "Release $releaseTag is still a draft and cannot be installed."
}

$wheelAsset = @($release.assets | Where-Object { $_.name -match '^unityagent_control_plane-.*\.whl$' }) | Select-Object -First 1
$checksumAsset = @($release.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' }) | Select-Object -First 1

if (-not $wheelAsset) {
    throw "Release $releaseTag does not contain a UnityAgent Control Plane wheel."
}
if (-not $checksumAsset) {
    throw "Release $releaseTag does not contain SHA256SUMS.txt."
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("UnityAgent-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

try {
    $wheelPath = Join-Path $tempRoot $wheelAsset.name
    $checksumPath = Join-Path $tempRoot "SHA256SUMS.txt"

    Write-Host "Downloading $($wheelAsset.name)..."
    Invoke-WebRequest -Uri $wheelAsset.browser_download_url -Headers $headers -OutFile $wheelPath -UseBasicParsing
    Invoke-WebRequest -Uri $checksumAsset.browser_download_url -Headers $headers -OutFile $checksumPath -UseBasicParsing

    $expectedHash = $null
    foreach ($line in Get-Content -LiteralPath $checksumPath) {
        if ($line -match '^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$') {
            if ($Matches[2].Trim() -eq $wheelAsset.name) {
                $expectedHash = $Matches[1].ToLowerInvariant()
                break
            }
        }
    }

    if (-not $expectedHash) {
        throw "SHA256SUMS.txt does not contain an entry for $($wheelAsset.name)."
    }

    $actualHash = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "SHA-256 verification failed for $($wheelAsset.name). Expected $expectedHash but got $actualHash."
    }

    Write-Host "SHA-256 verified. Installing UnityAgent Control Plane..."
    Invoke-Python -Python $python -Arguments @("-m", "pip", "install", "--user", "--upgrade", $wheelPath)
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

$userBaseOutput = & $python.Command @($python.Prefix + @("-c", "import site; print(site.getuserbase())"))
if ($LASTEXITCODE -ne 0) {
    throw "Unable to determine the current user's Python installation directory."
}
$userBase = ($userBaseOutput | Out-String).Trim()
if ([string]::IsNullOrWhiteSpace($userBase)) {
    throw "Unable to determine the current user's Python installation directory."
}

$scriptsRoot = Join-Path $userBase "Scripts"
$env:Path = "$scriptsRoot;$env:Path"

$unityAgent = Get-Command unity-agent -ErrorAction SilentlyContinue
if (-not $unityAgent) {
    throw "UnityAgent was installed but unity-agent was not found in $scriptsRoot."
}

& $unityAgent.Source --help | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Installed unity-agent failed its help verification."
}

$currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathParts = @()
if ($currentUserPath) {
    $pathParts = @($currentUserPath -split ';' | Where-Object { $_ -and $_.Trim() })
}

$alreadyPresent = @($pathParts | Where-Object {
    [string]::Equals($_.TrimEnd('\'), $scriptsRoot.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)
}).Count -gt 0

if (-not $alreadyPresent) {
    [Environment]::SetEnvironmentVariable("Path", (($pathParts + $scriptsRoot) -join ';'), "User")
}

Write-Host ""
Write-Host "UnityAgent $releaseTag installed successfully."
Write-Host "Control Plane: $($unityAgent.Source)"
Write-Host "Python Scripts: $scriptsRoot"
Write-Host ""
Write-Host "Next:"
Write-Host '  unity-agent doctor --project-path "C:\path\to\UnityProject" --format json --non-interactive'
Write-Host ""
Write-Host "Open a new PowerShell window if unity-agent is not immediately available in another terminal."

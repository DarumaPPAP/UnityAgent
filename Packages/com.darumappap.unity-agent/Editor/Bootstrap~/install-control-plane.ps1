param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseTag
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if ($PSVersionTable.PSVersion.Major -lt 5) {
    throw "PowerShell 5.1 or newer is required."
}
if ($ReleaseTag -notmatch '^v[A-Za-z0-9._-]+$') {
    throw "ReleaseTag must look like v0.0.6-beta."
}

$repository = "DarumaPPAP/UnityAgent"
$headers = @{
    "User-Agent" = "UnityAgent-Unity-Bootstrap"
    "Accept" = "application/vnd.github+json"
}

function Resolve-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @{ Command = $py.Source; Prefix = @("-3") } }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @{ Command = $python.Source; Prefix = @() } }
    throw "Python 3.10 or newer was not found. Install Python, then retry from UnityAgent Setup."
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Python,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Python.Command @($Python.Prefix + $Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
}

function Resolve-ExpectedHash {
    param(
        [Parameter(Mandatory = $true)][string]$ChecksumPath,
        [Parameter(Mandatory = $true)][string]$AssetName
    )

    foreach ($line in Get-Content -LiteralPath $ChecksumPath) {
        if ($line -notmatch '^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$') {
            continue
        }

        $entryPath = $Matches[2].Trim()
        $entryPath = $entryPath -replace '^[.][\\/]+', ''
        $entryName = [IO.Path]::GetFileName($entryPath)
        if ([string]::Equals($entryName, $AssetName, [StringComparison]::Ordinal)) {
            return $Matches[1].ToLowerInvariant()
        }
    }

    return $null
}

function Add-UserPathEntry {
    param([Parameter(Mandatory = $true)][string]$Directory)

    $currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathParts = @()
    if ($currentUserPath) {
        $pathParts = @($currentUserPath -split ';' | Where-Object { $_ -and $_.Trim() })
    }
    $alreadyPresent = @($pathParts | Where-Object {
        [string]::Equals($_.TrimEnd('\'), $Directory.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)
    }).Count -gt 0
    if (-not $alreadyPresent) {
        [Environment]::SetEnvironmentVariable("Path", (($pathParts + $Directory) -join ';'), "User")
    }
}

$python = Resolve-Python
& $python.Command @($python.Prefix + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"))
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or newer is required." }

Write-Host "Resolving UnityAgent release $ReleaseTag..."
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/$repository/releases/tags/$ReleaseTag" -Headers $headers -UseBasicParsing
if ($release.draft) { throw "Release $ReleaseTag is still a draft." }

$wheelAsset = @($release.assets | Where-Object { $_.name -match '^unityagent_control_plane-.*\.whl$' }) | Select-Object -First 1
$checksumAsset = @($release.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' }) | Select-Object -First 1
if (-not $wheelAsset) { throw "Release $ReleaseTag does not contain a Control Plane wheel." }
if (-not $checksumAsset) { throw "Release $ReleaseTag does not contain SHA256SUMS.txt." }

$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if ([string]::IsNullOrWhiteSpace($localAppData)) { $localAppData = $env:LOCALAPPDATA }
if ([string]::IsNullOrWhiteSpace($localAppData)) { throw "LOCALAPPDATA could not be resolved." }

$controlPlaneRoot = Join-Path $localAppData ("UnityAgent\ControlPlane\" + $ReleaseTag)
$venvRoot = Join-Path $controlPlaneRoot "venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$controlPlanePath = Join-Path $venvRoot "Scripts\unity-agent.exe"
$binRoot = Join-Path $localAppData "UnityAgent\bin"
$shimPath = Join-Path $binRoot "unity-agent.cmd"

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("UnityAgent-Bootstrap-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
try {
    $wheelPath = Join-Path $tempRoot $wheelAsset.name
    $checksumPath = Join-Path $tempRoot "SHA256SUMS.txt"
    Invoke-WebRequest -Uri $wheelAsset.browser_download_url -Headers $headers -OutFile $wheelPath -UseBasicParsing
    Invoke-WebRequest -Uri $checksumAsset.browser_download_url -Headers $headers -OutFile $checksumPath -UseBasicParsing

    $expectedHash = Resolve-ExpectedHash -ChecksumPath $checksumPath -AssetName ([string]$wheelAsset.name)
    if (-not $expectedHash) { throw "SHA256SUMS.txt has no entry for $($wheelAsset.name)." }

    $actualHash = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "SHA-256 verification failed. Expected $expectedHash but got $actualHash."
    }

    Write-Host "SHA-256 verified. Preparing isolated Control Plane runtime..."
    New-Item -ItemType Directory -Path $controlPlaneRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Invoke-Python -Python $python -Arguments @("-m", "venv", $venvRoot)
    }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Python virtual environment could not be created at $venvRoot."
    }

    & $venvPython -m pip install --disable-pip-version-check --upgrade $wheelPath
    if ($LASTEXITCODE -ne 0) { throw "Control Plane installation failed with exit code $LASTEXITCODE." }
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $controlPlanePath)) {
    throw "Control Plane was installed but unity-agent.exe could not be resolved at $controlPlanePath."
}

& $controlPlanePath --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Installed Control Plane failed help verification." }

New-Item -ItemType Directory -Path $binRoot -Force | Out-Null
$shimContent = "@echo off`r`n`"$controlPlanePath`" %*`r`n"
Set-Content -LiteralPath $shimPath -Value $shimContent -Encoding ASCII
Add-UserPathEntry -Directory $binRoot

[Environment]::SetEnvironmentVariable("UNITY_AGENT_CONTROL_PLANE", $controlPlanePath, "User")
$env:UNITY_AGENT_CONTROL_PLANE = $controlPlanePath
$env:Path = "$binRoot;$env:Path"

Write-Host "UnityAgent $ReleaseTag Control Plane installed successfully."
Write-Host "Control Plane: $controlPlanePath"
Write-Host "Stable command shim: $shimPath"
Write-Host "Runtime root: $controlPlaneRoot"

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

$python = Resolve-Python
& $python.Command @($python.Prefix + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"))
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or newer is required." }
Invoke-Python -Python $python -Arguments @("-m", "pip", "--version")

Write-Host "Resolving UnityAgent release $ReleaseTag..."
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/$repository/releases/tags/$ReleaseTag" -Headers $headers -UseBasicParsing
if ($release.draft) { throw "Release $ReleaseTag is still a draft." }

$wheelAsset = @($release.assets | Where-Object { $_.name -match '^unityagent_control_plane-.*\.whl$' }) | Select-Object -First 1
$checksumAsset = @($release.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' }) | Select-Object -First 1
if (-not $wheelAsset) { throw "Release $ReleaseTag does not contain a Control Plane wheel." }
if (-not $checksumAsset) { throw "Release $ReleaseTag does not contain SHA256SUMS.txt." }

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("UnityAgent-Bootstrap-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
try {
    $wheelPath = Join-Path $tempRoot $wheelAsset.name
    $checksumPath = Join-Path $tempRoot "SHA256SUMS.txt"
    Invoke-WebRequest -Uri $wheelAsset.browser_download_url -Headers $headers -OutFile $wheelPath -UseBasicParsing
    Invoke-WebRequest -Uri $checksumAsset.browser_download_url -Headers $headers -OutFile $checksumPath -UseBasicParsing

    $expectedHash = $null
    foreach ($line in Get-Content -LiteralPath $checksumPath) {
        if ($line -match '^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$' -and $Matches[2].Trim() -eq $wheelAsset.name) {
            $expectedHash = $Matches[1].ToLowerInvariant()
            break
        }
    }
    if (-not $expectedHash) { throw "SHA256SUMS.txt has no entry for $($wheelAsset.name)." }

    $actualHash = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "SHA-256 verification failed. Expected $expectedHash but got $actualHash."
    }

    Write-Host "SHA-256 verified. Installing UnityAgent Control Plane..."
    Invoke-Python -Python $python -Arguments @("-m", "pip", "install", "--user", "--upgrade", $wheelPath)
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

$scriptsRootOutput = & $python.Command @($python.Prefix + @("-c", "import sysconfig; print(sysconfig.get_path('scripts', scheme='nt_user'))"))
if ($LASTEXITCODE -ne 0) { throw "Unable to determine Python User Scripts directory." }
$scriptsRoot = ($scriptsRootOutput | Out-String).Trim()
$controlPlanePath = Join-Path $scriptsRoot "unity-agent.exe"
if (-not (Test-Path -LiteralPath $controlPlanePath)) {
    $resolved = Get-Command unity-agent -ErrorAction SilentlyContinue
    if ($resolved) { $controlPlanePath = $resolved.Source }
}
if (-not (Test-Path -LiteralPath $controlPlanePath)) {
    throw "Control Plane was installed but unity-agent.exe could not be resolved."
}

& $controlPlanePath --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Installed Control Plane failed help verification." }

[Environment]::SetEnvironmentVariable("UNITY_AGENT_CONTROL_PLANE", $controlPlanePath, "User")
$env:UNITY_AGENT_CONTROL_PLANE = $controlPlanePath

$currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathParts = @()
if ($currentUserPath) { $pathParts = @($currentUserPath -split ';' | Where-Object { $_ -and $_.Trim() }) }
$alreadyPresent = @($pathParts | Where-Object {
    [string]::Equals($_.TrimEnd('\'), $scriptsRoot.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)
}).Count -gt 0
if (-not $alreadyPresent) {
    [Environment]::SetEnvironmentVariable("Path", (($pathParts + $scriptsRoot) -join ';'), "User")
}

Write-Host "UnityAgent $ReleaseTag Control Plane installed successfully."
Write-Host "Control Plane: $controlPlanePath"

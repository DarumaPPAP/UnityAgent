# UnityAgent remote bootstrap installer.
#
# Intended usage from Windows PowerShell:
#   irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/migration/unity-artist-cli-v2/scripts/install-remote.ps1 | iex
#
# The bootstrap installs the host Control Plane from this GitHub repository into
# the current user's Python environment. Unity UPM and Codex Plugin entries remain
# GitHub-backed package/plugin surfaces and are not copied by this script.

$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSVersion.Major -lt 5) {
    throw "PowerShell 5.1 or newer is required."
}

$repository = "DarumaPPAP/UnityAgent"
$requestedRef = if ($env:UNITY_AGENT_REF) { $env:UNITY_AGENT_REF.Trim() } else { "v0.0.1-beta" }
if ([string]::IsNullOrWhiteSpace($requestedRef) -or $requestedRef -notmatch '^[A-Za-z0-9._/-]+$') {
    throw "UNITY_AGENT_REF must be a safe Git ref such as v0.0.1-beta or main."
}

$python = Get-Command py -ErrorAction SilentlyContinue
$pythonArgs = @()
if ($python) {
    $pythonArgs = @("-3")
}
else {
    $python = Get-Command python -ErrorAction SilentlyContinue
}

if (-not $python) {
    throw "Python 3.10 or newer was not found. Install Python, then rerun this command."
}

& $python.Source @pythonArgs -m pip --version | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Python pip is unavailable. Enable pip for the selected Python installation, then rerun this command."
}

$source = "git+https://github.com/$repository.git@$requestedRef"
Write-Host "Installing UnityAgent Control Plane from $repository@$requestedRef..."
& $python.Source @pythonArgs -m pip install --user --upgrade $source
if ($LASTEXITCODE -ne 0) {
    throw "UnityAgent Control Plane installation failed."
}

$userBase = (& $python.Source @pythonArgs -c "import site; print(site.getuserbase())" | Out-String).Trim()
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

Write-Host "Installed unity-agent from $repository@$requestedRef."
Write-Host "Current user Python Scripts: $scriptsRoot"
Write-Host "Open a new PowerShell window, then run: unity-agent setup --help"
Write-Host "Unity UPM and Codex Plugin remain available from the same GitHub repository."

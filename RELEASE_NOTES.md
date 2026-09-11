# UnityAgent 0.0.6-beta

UnityAgent 0.0.6-beta turns `UnityAgent > Setup` into the primary installation surface instead of requiring users to preinstall the Control Plane from a terminal.

## Unity-side Control Plane Bootstrap

When the Control Plane is not installed, the Setup Window now presents an explicit primary action:

```text
Install Control Plane
```

The Bootstrap path is intentionally narrow. It installs only the UnityAgent Control Plane and does not install Codex plugins or mutate other Providers.

```text
UnityAgent UPM
  ↓ bootstrap-only path
package-local install-control-plane.ps1
  ↓
GitHub Release wheel + SHA256SUMS.txt
  ↓ SHA-256 verification
pip --user
  ↓
unity-agent.exe
  ↓
UNITY_AGENT_CONTROL_PLANE
```

The package-local PowerShell script is shipped inside the immutable UPM package and downloads only the pinned Release wheel and checksum file.

## Setup Window redesign

The Editor window was reorganized around setup state instead of raw logs.

```text
UnityAgent Setup

Setup Readiness
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. UnityAgent Control Plane
   READY / ACTION REQUIRED / INSTALLING
   Resolved Path
   Install / Rediscover / Browse / Clear Override

2. Codex CLI
   READY / NOT FOUND
   Resolved Path
   Rediscover / Browse / Clear Override

3. Codex Integration
   Check Status
   Install / Repair Plugin

Current Status
Diagnostics / Raw response
Advanced
```

The layout is responsive to Unity's light/dark Editor themes and keeps actionable state visible while raw stdout/stderr remains collapsed under Diagnostics.

## Bootstrap boundary

The existing five-layer runtime remains unchanged after bootstrap:

```text
Unity Window
  ↓
UnityAgent Control Plane
  ↓
Setup Plan / Approval
  ↓
Installer Provider
  ↓
Provider / Codex CLI
  ↓
InstallReceipt / Evidence
```

CI now enforces that:

- Control Plane bootstrap is present and version-pinned.
- Bootstrap executes the package-local script.
- Bootstrap cannot contain direct Codex Plugin or UnityArtistCLI mutation commands.
- The bootstrap script verifies `SHA256SUMS.txt` with `Get-FileHash`.
- The bootstrap script installs with `pip --user` and persists `UNITY_AGENT_CONTROL_PLANE`.
- Normal Unity Entry code still cannot invoke Codex Plugin or Provider commands directly.

## Release Workflow UX fix

The Release Workflow no longer asks for a free-text tag.

Previously a stale or malformed value such as:

```text
0.0.2-beta
```

could make the initial `set -euo pipefail` contract check terminate with only a generic exit code.

The workflow now derives the immutable release tag directly from `main/VERSION`:

```text
VERSION = 0.0.6-beta
        ↓
RELEASE_TAG = v0.0.6-beta
```

The only manual input is:

```text
confirm_release = true
```

Wrong historical tags and missing `v` prefixes are therefore no longer user-entered release state.

## Distribution

This release publishes:

- UnityAgent UPM package (`com.darumappap.unity-agent`)
- Codex `unity-agent` plugin archive
- Python Control Plane wheel and source distribution
- `SHA256SUMS.txt`

The Release Workflow verifies that the packed UPM `.tgz` contains the Control Plane Bootstrap runner, its `.meta`, and the package-local bootstrap script before the immutable tag is created.

## Provider pinning

UnityAgent `0.0.6-beta` continues to pin UnityArtistCLI independently to `v0.0.1-beta`.

```text
UnityAgent channel      = 0.0.6-beta
UnityAgent Codex plugin = 0.0.6-beta
UnityArtistCLI provider = 0.0.1-beta
```

## Safety and compatibility

- Toolchain mutation remains `Plan -> Approval -> Apply -> Evidence` after the Control Plane exists.
- Codex Marketplace ID remains `unity-agent`.
- Canonical Codex plugin identifier remains `unity-agent@unity-agent`.
- Control Plane Bootstrap is the only pre-Control-Plane mutation path and is scoped to the Control Plane itself.
- Unknown, stale, unavailable, or conflicting Marketplace states continue to fail closed.
- Existing beta releases remain immutable.

## License

UnityAgent is distributed under the MIT License.

## Version contract

The canonical release version is `0.0.6-beta`.

- UPM package: `0.0.6-beta`
- Codex plugin: `0.0.6-beta`
- Python package: `0.0.6b0`
- Codex Marketplace: `unity-agent`
- UnityArtistCLI provider: `v0.0.1-beta`
- License: `MIT`

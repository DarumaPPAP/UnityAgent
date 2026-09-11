# UnityAgent 0.0.2-beta

UnityAgent 0.0.2-beta focuses on making the beta installable and testable from the Unity Editor while preserving the single-Control-Plane architecture.

## Highlights

- UnityAgent Setup Window can inspect, install, and repair the Codex `unity-agent` plugin through the approval-gated Control Plane.
- Codex Marketplace ID is now dedicated to UnityAgent: `unity-agent`.
- The canonical Codex plugin identifier is now `unity-agent@unity-agent`.
- The generic `personal` Marketplace name is no longer used by UnityAgent.
- The public README now presents the recommended Unity-first setup flow and includes Unity, Codex, Release, CI, and MIT badges.
- The repository is now explicitly distributed under the MIT License.
- `main/scripts/install.ps1` resolves the newest published UnityAgent prerelease by default while still supporting an explicit `UNITY_AGENT_TAG` override.

## Unity-first Codex setup

The recommended Codex setup route is now:

```text
UnityAgent > Setup
  ↓
Codex Pluginをインストール / 修復
  ↓
UnityAgent Control Plane
  ↓
Setup Plan / Approval
  ↓
Installer Provider
  ↓
Codex CLI
  ↓
unity-agent@unity-agent
  ↓
InstallReceipt / Evidence
```

The Unity Entry Layer does not invoke `codex plugin ...` directly. The five-layer boundary remains enforced by validation.

## Distribution

This release publishes the following artifacts from the same immutable tag:

- UnityAgent UPM package (`com.darumappap.unity-agent`)
- Codex `unity-agent` plugin archive
- Python Control Plane wheel and source distribution
- SHA-256 checksums for every published artifact

## Provider pinning

UnityAgent `0.0.2-beta` keeps UnityArtistCLI pinned to the immutable `v0.0.1-beta` release.

The UnityAgent release channel and Provider product versions are separate contracts:

```text
UnityAgent channel     = 0.0.2-beta
UnityAgent Codex plugin = 0.0.2-beta
UnityArtistCLI provider = 0.0.1-beta
```

This keeps the UnityAgent beta reproducible without pretending that every Provider must share the Control Plane version.

## Safety and compatibility

- Toolchain mutation remains `Plan -> Approval -> Apply -> Evidence`.
- Unknown, unavailable, stale, or conflicting Marketplace states fail closed.
- An existing unrelated Marketplace is never silently retargeted.
- InstallReceipt and toolchain setup contracts are versioned with the UnityAgent release channel.
- Published release artifacts remain immutable.

## License

UnityAgent is distributed under the MIT License. See `LICENSE` in the repository and release source archive.

## Beta limitations

- This is still a beta contract and breaking changes may occur before GA.
- UnityArtistCLI remains on `v0.0.1-beta` until a separately validated provider release is published.
- Release signing is not yet a GA-grade trust mechanism; beta artifacts are published with SHA-256 checksums.

## Version contract

The canonical release version is `0.0.2-beta`.

- UPM package: `0.0.2-beta`
- Codex plugin: `0.0.2-beta`
- Python package: `0.0.2b0`
- Codex Marketplace: `unity-agent`
- License: `MIT`

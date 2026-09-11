# UnityAgent 0.0.3-beta

UnityAgent 0.0.3-beta is a packaging-fix beta for the Unity Editor integration introduced in 0.0.2-beta.

## Critical UPM fix

`v0.0.2-beta` shipped the UnityAgent UPM source without the Unity `.meta` files required for assets inside an immutable Package Manager package. Unity therefore reported messages such as:

```text
Asset Packages/com.darumappap.unity-agent/Editor has no meta file, but it's in an immutable folder. The asset will be ignored.
```

`v0.0.3-beta` fixes this by shipping stable `.meta` files for:

- `Editor/`
- `package.json`
- `Editor/DarumaPPAP.UnityAgent.Editor.asmdef`
- `Editor/UnityAgentControlPlaneClient.cs`
- `Editor/UnityAgentSetupWindow.cs`

The corresponding GUIDs are committed to the repository and remain stable across installs.

## Release hardening

Two independent guards now prevent this regression:

1. The repository validator requires every imported UnityAgent UPM asset/folder to have a corresponding `.meta` file with a canonical GUID; folder metas must declare `folderAsset: yes`.
2. The Release Workflow inspects the packed `UnityAgent-UPM-<version>.tgz` artifact and fails before tag creation if required `.meta` files are absent.

## Unity-first Codex setup

The recommended setup route remains:

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

The Unity Entry Layer does not invoke `codex plugin ...` directly.

## Distribution

This release publishes the following artifacts from the same immutable tag:

- UnityAgent UPM package (`com.darumappap.unity-agent`)
- Codex `unity-agent` plugin archive
- Python Control Plane wheel and source distribution
- SHA-256 checksums for every published artifact

## Provider pinning

UnityAgent `0.0.3-beta` continues to pin UnityArtistCLI to the immutable `v0.0.1-beta` release.

```text
UnityAgent channel      = 0.0.3-beta
UnityAgent Codex plugin = 0.0.3-beta
UnityArtistCLI provider = 0.0.1-beta
```

UnityAgent release channel and Provider product versions remain separate contracts.

## Safety and compatibility

- Toolchain mutation remains `Plan -> Approval -> Apply -> Evidence`.
- Codex Marketplace ID remains `unity-agent`.
- Canonical Codex plugin identifier remains `unity-agent@unity-agent`.
- Unknown, unavailable, stale, or conflicting Marketplace states fail closed.
- InstallReceipt and Toolchain Setup contracts are versioned with the UnityAgent release channel.
- Published release artifacts remain immutable; `v0.0.2-beta` is not modified or replaced.

## License

UnityAgent is distributed under the MIT License.

## Beta limitations

- This is still a beta contract and breaking changes may occur before GA.
- UnityArtistCLI remains on `v0.0.1-beta` until a separately validated provider release is published.
- Release signing is not yet a GA-grade trust mechanism; beta artifacts are published with SHA-256 checksums.

## Version contract

The canonical release version is `0.0.3-beta`.

- UPM package: `0.0.3-beta`
- Codex plugin: `0.0.3-beta`
- Python package: `0.0.3b0`
- Codex Marketplace: `unity-agent`
- License: `MIT`

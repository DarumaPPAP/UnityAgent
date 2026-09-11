# UnityAgent 0.0.4-beta

UnityAgent 0.0.4-beta improves the Unity-side Codex setup experience after beta testing exposed two practical problems: Unity could fail to discover an installed Codex CLI, and setup failures were difficult to understand from the raw Control Plane response.

## Codex CLI discovery

UnityAgent Setup no longer relies only on the PATH inherited by Unity Hub.

The Unity Editor now resolves Codex CLI through a dedicated path resolver using the following strategy:

```text
Manual EditorPrefs override
  ↓
UNITY_AGENT_CODEX_CLI / CODEX_CLI
  ↓
Common Windows npm/native locations
  ↓
NVM / user-local locations
  ↓
PATH / where.exe / which
  ↓
codex --version validation
```

The resolver supports Windows `codex.exe`, `codex.cmd`, `codex.bat`, and `codex.ps1` launch surfaces. A user-selected override is persisted and treated strictly: if that override becomes invalid, UnityAgent reports it instead of silently switching to another CLI installation.

The Control Plane also accepts an explicit `--codex-path` and keeps its own PATH/common-location fallback so Unity UI and headless setup both remain usable.

## Unity Setup UX

`UnityAgent > Setup` now exposes:

```text
Codex CLI
├─ Resolved Path
├─ 再検出
├─ 参照...
└─ Override解除

Codex Integration
├─ 状態を確認
└─ Codex Pluginをインストール / 修復

Status
└─ short human-readable diagnosis

詳細ログ / Raw response
├─ stderr / process error
├─ Control Plane JSON
└─ copy / clear
```

Common states such as `codex_cli_unavailable`, `plugin_not_installed`, `plugin_not_enabled`, version mismatch, and Marketplace collision are converted to actionable messages while raw evidence remains available for debugging.

## Architecture boundary

The Unity Editor still does not run `codex plugin ...` mutation commands directly.

```text
Unity Window
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

Unity-side path resolution is only environment discovery/input. Plugin installation remains owned by the Installer Provider.

## Windows command shim handling

The Installer Provider now handles npm-style Windows command shims when invoking Codex. `.cmd` / `.bat` launchers are executed through the Windows command interpreter and failures include the executable and command-level diagnostic instead of collapsing into an unreadable generic error.

## UPM integrity

The `.meta` fix introduced in `v0.0.3-beta` remains in place. The new `UnityAgentCodexPathResolver.cs` also ships with a committed stable `.meta` file, and the Release Workflow verifies that this meta is present in the packed UPM `.tgz` before tag creation.

## Distribution

This release publishes:

- UnityAgent UPM package (`com.darumappap.unity-agent`)
- Codex `unity-agent` plugin archive
- Python Control Plane wheel and source distribution
- SHA-256 checksums for every published artifact

## Provider pinning

UnityAgent `0.0.4-beta` continues to pin UnityArtistCLI independently to `v0.0.1-beta`.

```text
UnityAgent channel      = 0.0.4-beta
UnityAgent Codex plugin = 0.0.4-beta
UnityArtistCLI provider = 0.0.1-beta
```

## Safety and compatibility

- Toolchain mutation remains `Plan -> Approval -> Apply -> Evidence`.
- Codex Marketplace ID remains `unity-agent`.
- Canonical Codex plugin identifier remains `unity-agent@unity-agent`.
- Invalid manual Codex path overrides fail visibly instead of silently selecting another executable.
- Unknown, stale, unavailable, or conflicting Marketplace states continue to fail closed.
- `v0.0.2-beta` and `v0.0.3-beta` remain immutable and are not replaced.

## License

UnityAgent is distributed under the MIT License.

## Beta limitations

- This is still a beta contract and breaking changes may occur before GA.
- UnityArtistCLI remains on `v0.0.1-beta` until a separately validated provider release is published.
- Release signing is not yet a GA-grade trust mechanism; beta artifacts are published with SHA-256 checksums.

## Version contract

The canonical release version is `0.0.4-beta`.

- UPM package: `0.0.4-beta`
- Codex plugin: `0.0.4-beta`
- Python package: `0.0.4b0`
- Codex Marketplace: `unity-agent`
- License: `MIT`

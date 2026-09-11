# UnityAgent 0.0.5-beta

UnityAgent 0.0.5-beta fixes a Unity-side setup failure where `UnityAgent > Setup` could detect Codex CLI correctly but still fail before any setup work because the Unity Editor could not resolve the `unity-agent` Control Plane executable from its inherited PATH.

## Control Plane discovery

The Setup Window now resolves the Control Plane independently from Codex CLI.

```text
Manual EditorPrefs override
  ↓
UNITY_AGENT_CONTROL_PLANE
  ↓
Persisted User environment
  ↓
Python User Scripts
  ↓
Process PATH / User PATH
```

The Window shows the resolved executable path and source, and provides `再検出`, `参照...`, and `Override解除` controls. Setup actions remain disabled while the Control Plane is unresolved, so users no longer hit an opaque `Win32Exception` from a bare `unity-agent` command.

## Stable installer hint

`scripts/install.ps1` now persists the exact installed `unity-agent.exe` path as the User-scoped `UNITY_AGENT_CONTROL_PLANE` environment variable in addition to updating User PATH.

This is specifically intended for Unity Hub / Unity Editor processes that were launched before the installer updated PATH. The Setup Window reads the persisted User environment directly, so a full shell/Hub restart is no longer the primary recovery path.

## Unity Setup UX

`UnityAgent > Setup` now presents both host dependencies explicitly:

```text
UnityAgent Control Plane
├─ Resolved Path
├─ 再検出
├─ 参照...
└─ Override解除

Codex CLI
├─ Resolved Path
├─ 再検出
├─ 参照...
└─ Override解除

Codex Integration
├─ 状態を確認
└─ Codex Pluginをインストール / 修復
```

Human-readable status remains the default surface, while raw stdout/stderr and Control Plane JSON stay available under `詳細ログ / Raw response`.

## Architecture boundary

The discovery improvement does not introduce a second execution path.

```text
Unity Window
  ↓
resolved Control Plane executable
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

The new `UnityAgentControlPlanePathResolver` is filesystem/environment discovery only. It does not execute Providers or Codex. CI now enforces that the resolver remains process-free and that the Setup Window uses it instead of a bare `unity-agent` command.

## Codex CLI discovery

The `v0.0.4-beta` Codex path improvements remain in place:

- explicit manual override
- `UNITY_AGENT_CODEX_CLI` / `CODEX_CLI`
- Windows npm/native locations
- NVM / user-local locations
- PATH fallback
- `.exe`, `.cmd`, `.bat`, `.ps1` handling
- Installer Provider-side `codex --version` validation
- human-readable failure diagnostics

## UPM integrity

All UnityAgent Editor assets, including `UnityAgentControlPlanePathResolver.cs`, ship with committed stable `.meta` files. The Release Workflow validates the packed UPM `.tgz` before tag creation and fails if the new resolver meta is missing.

## Distribution

This release publishes:

- UnityAgent UPM package (`com.darumappap.unity-agent`)
- Codex `unity-agent` plugin archive
- Python Control Plane wheel and source distribution
- SHA-256 checksums for every published artifact

## Provider pinning

UnityAgent `0.0.5-beta` continues to pin UnityArtistCLI independently to `v0.0.1-beta`.

```text
UnityAgent channel      = 0.0.5-beta
UnityAgent Codex plugin = 0.0.5-beta
UnityArtistCLI provider = 0.0.1-beta
```

## Safety and compatibility

- Toolchain mutation remains `Plan -> Approval -> Apply -> Evidence`.
- Codex Marketplace ID remains `unity-agent`.
- Canonical Codex plugin identifier remains `unity-agent@unity-agent`.
- Invalid manual Control Plane/Codex overrides fail visibly instead of silently retargeting.
- Unknown, stale, unavailable, or conflicting Marketplace states continue to fail closed.
- Published Beta releases remain immutable and are not replaced.

## License

UnityAgent is distributed under the MIT License.

## Beta limitations

- This is still a beta contract and breaking changes may occur before GA.
- UnityArtistCLI remains on `v0.0.1-beta` until a separately validated provider release is published.
- Release signing is not yet a GA-grade trust mechanism; beta artifacts are published with SHA-256 checksums.

## Version contract

The canonical release version is `0.0.5-beta`.

- UPM package: `0.0.5-beta`
- Codex plugin: `0.0.5-beta`
- Python package: `0.0.5b0`
- Codex Marketplace: `unity-agent`
- License: `MIT`

# UnityAgent 0.0.7-beta

UnityAgent 0.0.7-beta focuses on a cleaner Unity-side setup experience and a more reliable managed runtime/bootstrap path.

## Branded Setup Window

`UnityAgent > Setup` now uses the UnityAgent visual identity directly inside the Editor.

- Added the UnityAgent logo as a package asset and hardened Git UPM loading.
- Removed the baked white logo background and enabled alpha transparency.
- Enlarged the hero/header area and strengthened the red/charcoal visual hierarchy.
- Refined Setup Readiness, Control Plane, Codex CLI, Codex Integration, and Current Status cards.
- Added clearer path presentation, copy action, spacing, badges, and action hierarchy.
- Kept Diagnostics / Raw response and Advanced collapsed so the primary setup path remains readable.

The underlying Control Plane / approval / installer-provider / evidence flow remains unchanged.

## Managed Control Plane runtime

The Control Plane bootstrap and stable installer now use an isolated LocalAppData runtime instead of a legacy `pip --user` layout.

```text
%LOCALAPPDATA%/UnityAgent/ControlPlane/v0.0.7-beta/venv/
```

A stable shim remains available under:

```text
%LOCALAPPDATA%/UnityAgent/bin/unity-agent.cmd
```

`UNITY_AGENT_CONTROL_PLANE` continues to be persisted as the stable discovery hint used by the Unity Editor package.

## Codex Desktop discovery

UnityAgent now searches additional managed Codex Desktop locations before requiring a manual override, including standalone/package-managed Desktop runtimes and the normal OpenAI Codex program location.

The resolver remains discovery-only: Unity Entry code still does not execute Codex directly.

## Installer and checksum hardening

Both the package-local bootstrap installer and the stable installer now share stricter release verification behavior.

- Canonical checksum parsing accepts normalized basename entries and legacy `./` / `.\` prefixes.
- Release artifacts are SHA-256 verified before installation.
- Managed runtime installation remains isolated from user Python package state.
- UPM package validation checks required bootstrap and `.meta` files before release.

## Unity package reliability

Additional safeguards cover Git UPM and Unity 6 Editor behavior.

- Stable `.meta` coverage for package assets/folders.
- Fully-qualified `UnityEditor.PackageManager.PackageInfo` usage to avoid `PackageInfo` ambiguity.
- Setup logo loading retries package-path/GUID resolution across import and focus timing.
- Packed UPM contents are validated in CI.

## Release artifacts

The v0.0.7-beta prerelease publishes:

- `UnityAgent-UPM-0.0.7-beta.tgz`
- `UnityAgent-CodexPlugin-0.0.7-beta.zip`
- `unityagent_control_plane-0.0.7b0-py3-none-any.whl`
- `unityagent_control_plane-0.0.7b0.tar.gz`
- `SHA256SUMS.txt`

UPM Git URL:

```text
https://github.com/DarumaPPAP/UnityAgent.git?path=/Packages/com.darumappap.unity-agent#v0.0.7-beta
```

This remains a beta release and may include breaking changes before 1.0.

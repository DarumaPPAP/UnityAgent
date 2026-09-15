from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = "0.0.6-beta"
NEW = "0.0.7-beta"
OLD_PY = "0.0.6b0"
NEW_PY = "0.0.7b0"

TARGETS = [
    ".agents/plugins/unity-agent/.codex-plugin/plugin.json",
    ".agents/plugins/unity-agent/plugin.json",
    "Packages/com.darumappap.unity-agent/Editor/Bootstrap~/install-control-plane.ps1",
    "Packages/com.darumappap.unity-agent/Editor/UnityAgentControlPlaneBootstrap.cs",
    "Packages/com.darumappap.unity-agent/Editor/UnityAgentSetupWindow.cs",
    "Packages/com.darumappap.unity-agent/package.json",
    "Persistence/Install/receipt_store.py",
    "README.md",
    "Runtime/Contracts/install-receipt.schema.yaml",
    "Runtime/Contracts/toolchain-setup-request.schema.yaml",
    "Runtime/Tests/test_control_plane.py",
    "Runtime/Tests/test_installer_provider.py",
    "Runtime/Tooling/Providers/Installer/codex_plugin_installer.py",
    "Runtime/Tooling/Providers/Installer/installer_provider.py",
    "Runtime/Tooling/Providers/Installer/release_installer.py",
    "Runtime/Tooling/Providers/Installer/toolchain_installer.py",
    "Tools/LayerBoundaryValidator/validate_layer_boundaries.py",
    "Tools/unity_agent_cli.py",
    "VERSION",
    "scripts/install.ps1",
]

for relative in TARGETS:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if OLD not in text:
        raise SystemExit(f"expected {OLD!r} in {relative}")
    path.write_text(text.replace(OLD, NEW), encoding="utf-8")

pyproject = ROOT / "pyproject.toml"
text = pyproject.read_text(encoding="utf-8")
if OLD_PY not in text:
    raise SystemExit(f"expected {OLD_PY!r} in pyproject.toml")
pyproject.write_text(text.replace(OLD_PY, NEW_PY), encoding="utf-8")

release_notes = ROOT / "RELEASE_NOTES.md"
release_notes.write_text(
    """# UnityAgent 0.0.7-beta

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

- Canonical checksum parsing accepts normalized basename entries and legacy `./` / `.\\` prefixes.
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
""",
    encoding="utf-8",
)

print("Prepared UnityAgent 0.0.7-beta canonical version and release notes.")

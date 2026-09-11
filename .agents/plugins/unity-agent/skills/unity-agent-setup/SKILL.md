---
name: unity-agent-setup
description: Set up and verify the UnityAgent runtime plus the UnityArtistCLI provider.
---

# UnityAgent setup

Use this skill when a project needs the UnityAgent runtime or a Unity toolchain
configured. This skill is an Entry Layer and must call the UnityAgent Control
Plane only.

Install the UnityAgent host directly from GitHub on Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/migration/unity-artist-cli-v2/scripts/install-remote.ps1 | iex
```

The remote bootstrap installs the host Control Plane into the current user's Python environment
and adds its Scripts directory to User PATH. A repository checkout may instead use
`python -m pip install -e .`. The UnityAgent UPM package and this Codex Plugin are separate GitHub
surfaces. Both Entry surfaces use the same Control Plane contracts.

## Control Plane setup

1. Run `unity-agent doctor --project-path <project> --format json --non-interactive`.
2. Request an exact setup plan with `unity-agent setup --operation plan --project-path <project> --format json --non-interactive`.
3. Present the plan and obtain explicit approval in Unity UI or Codex.
4. Apply only with the returned `plan_id` and approval reference:
   `unity-agent setup --operation apply --expected-plan-id <plan_id> --approval-ref <approval_ref> --project-path <project> --format json --non-interactive`.
5. Keep the returned `InstallReceipt` and Evidence references; re-run `unity-agent doctor` through the same Control Plane.

UnityAgent remains the Architect, Commander and Loop Owner. It must submit a semantic `CapabilityRequest`; it must not call a provider directly or create another Player/Provider registry.

The underlying Official Unity CLI, UnityArtistCLI and Installer Provider
commands are never invoked from this Entry skill. Provider identity is resolved
inside the existing Runtime Provider Registry and ToolBroker.

## Safety

- Use an explicit project path and bounded timeout.
- Keep `--format json` for runtime integration; reject malformed or partial results.
- Treat unknown environment facts as unavailable, never as approval to mutate.
- Use `plan -> preview -> approval -> apply -> capture -> evaluate/refine` for visual changes.
- Do not use shell/eval/raw YAML commands or bypass the existing Runtime Guard, ToolBroker, Resolver, Dispatcher, Provider Adapter or Evidence Normalizer.

## Failure handling

Report the structured status and error code. `unsupported`, `unavailable`, `stale_revision`, and `approval_required` are different outcomes; do not convert them to success.

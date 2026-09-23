---
name: unity-agent-setup
description: Use when setting up or verifying the UnityAgent Control Plane, Unity toolchain, UnityArtistCLI, or UnityAgent Codex Plugin for a Unity project. Routes all setup through the existing Control Plane and Installer Provider. Does not invoke Providers directly.
---

# UnityAgent setup

Use this skill when a project needs the UnityAgent runtime or toolchain configured. This skill is an Entry Layer and calls the UnityAgent Control Plane only.

For interactive Unity users, prefer `UnityAgent > Setup`. The Unity Window can check and install / repair the UnityAgent Codex Plugin while preserving the same Plan / Approval / InstallReceipt contract used by the CLI.

Install the UnityAgent host directly from GitHub on Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1 | iex
```

The stable bootstrap selects the latest published UnityAgent prerelease, verifies its
wheel checksum, and installs the host Control Plane into an isolated per-release virtual
environment under LocalAppData. It creates a user-path command shim. Set `UNITY_AGENT_TAG`
to pin a specific immutable release. A repository checkout may instead use
`python -m pip install -e .` for local development. The UnityAgent UPM package and this
Codex Plugin are separate GitHub surfaces; both use the same Control Plane contracts.

## Control Plane setup

1. Run `unity-agent doctor --project-path <project> --format json --non-interactive`.
2. Request an exact setup plan and save the full JSON response:
   `unity-agent setup --operation plan --project-path <project> --format json --non-interactive > approved-plan.json`.
3. Present that exact plan and obtain explicit approval in Unity UI or Codex.
4. Apply only with the returned `plan_id`, the approval reference, and the approved plan file:
   `unity-agent setup --operation apply --expected-plan-id <plan_id> --approval-ref <approval_ref> --approved-plan approved-plan.json --project-path <project> --format json --non-interactive`.
5. Keep the returned `InstallReceipt` and Evidence references; re-run `unity-agent doctor` through the same Control Plane.

For UnityAgent Codex Plugin setup, scope the request with `--product unity_agent_codex_plugin`. Codex CLI absence, marketplace collisions, malformed JSON output, stale plans, and failed post-install verification must remain blocked outcomes.

UnityAgent remains the Architect, Commander and Loop Owner. It must submit semantic requests through the existing Runtime and must not create another Player / Provider registry.

The underlying Official Unity CLI, UnityArtistCLI, Codex CLI and Installer Provider commands are never invoked from this Entry skill. Provider and installer implementation details stay behind the Control Plane / ToolBroker boundary.

## Safety

- Use an explicit project path and bounded timeout.
- Keep `--format json` for runtime integration; reject malformed or partial results.
- Treat unknown environment facts as unavailable, never as approval to mutate.
- Never retarget or overwrite an unrelated Codex marketplace silently.
- Reuse the exact approved plan and `plan_id`; do not reconstruct a mutation plan after approval.
- Use `plan -> preview -> approval -> apply -> capture -> evaluate/refine` for visual changes.
- Do not use shell/eval/raw YAML commands or bypass the existing Runtime Guard, ToolBroker, Resolver, Dispatcher, Provider Adapter or Evidence Normalizer.

## Failure handling

Report the structured status and error code. `unsupported`, `unavailable`, `stale_revision`, `blocked_by_dependency`, `blocked_by_approval`, and execution failures are different outcomes; do not convert them to success.

## Output Contract

Report the Control Plane status and the explicit project path. For Apply operations, include the approved plan ID, approval reference, InstallReceipt, and Evidence references. If setup is blocked, state the structured failure status and the unmet precondition.

## Checklist

- [ ] Confirm the project path and current Control Plane state.
- [ ] Present the exact setup plan before requesting approval.
- [ ] Apply only the approved plan with its original plan ID and approval reference.
- [ ] Verify the resulting installation through the same Control Plane and retain its receipt.

## Common Mistakes

- Running Unity, Codex, or installer Provider commands directly from the Entry skill.
- Applying a reconstructed or stale plan after approval.
- Treating unknown facts, missing receipts, or failed post-install checks as success.
- Replacing an existing marketplace or project binding without explicit approval.

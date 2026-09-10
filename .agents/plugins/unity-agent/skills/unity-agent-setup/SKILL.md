---
name: unity-agent-setup
description: Set up and verify the UnityAgent runtime plus the UnityArtistCLI provider.
---

# UnityAgent setup

Use this skill when a project needs the UnityAgent runtime or the UnityArtistCLI provider enabled.

## Provider-first setup

1. Check `unity --version` and `unity artist version --format json --non-interactive`.
2. Inspect `unity artist doctor --project-path <project> --format json --non-interactive` before mutation.
3. If the project is supported, install or verify the `com.darumappap.unity-artist` package with `unity artist install`.
4. Re-run doctor and keep the JSON response as environment evidence.

UnityAgent remains the Architect, Commander and Loop Owner. It must submit a semantic `CapabilityRequest`; it must not call a provider directly or create another Player/Provider registry.

## Safety

- Use an explicit project path and bounded timeout.
- Keep `--format json` for runtime integration; reject malformed or partial results.
- Treat unknown environment facts as unavailable, never as approval to mutate.
- Use `plan -> preview -> approval -> apply -> capture -> evaluate/refine` for visual changes.
- Do not use shell/eval/raw YAML commands or bypass the existing Runtime Guard, ToolBroker, Resolver, Dispatcher, Provider Adapter or Evidence Normalizer.

## Failure handling

Report the structured status and error code. `unsupported`, `unavailable`, `stale_revision`, and `approval_required` are different outcomes; do not convert them to success.

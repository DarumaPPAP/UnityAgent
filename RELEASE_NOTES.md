# UnityAgent 0.0.8-beta

UnityAgent 0.0.8-beta promotes the current typed Control Plane and Specialist architecture into the next beta distribution.

## Entry v2 production boundary

- Typed v2 intents are the production execution entry.
- Caller-supplied Context identity, route, capability and runtime handoff are rejected instead of trusted.
- v1 remains an explicit validation-compatibility surface.

## Production Specialists

Consumer Catalog v3 currently exposes:

- ArtistSubAgent — provider-backed through `unity_artist_cli`
- GraphicsSubAgent — providerless reasoning / read-only analysis
- WorldCreatorSubAgent — providerless reasoning / planning-only
- PerformanceSubAgent — providerless reasoning / read-only analysis

Reasoning specialists execute through UnityAgent's CodexRunner contract and do not use fake semantic providers.

## Hub contract alignment

- Hub Snapshot v3 / Manifest v5 are accepted through the Offline Import Gate.
- Hub registration is not treated as runtime installation, compatibility, project binding, eligibility or readiness.
- UnitySubAgentHub and individual SubAgents do not publish independent releases.
- This UnityAgent release pins `DarumaPPAP/UnitySubAgentHub@61d3fad2e0aef50b69fc76fbbd839aca076de19f` as source provenance.
- Artist backend host/package bytes and the consumer-neutral Hub Snapshot are built from that exact commit and published as UnityAgent release assets.

## Fixed Full E2E capability

The bounded `fixed_full_e2e_probe` intent verifies:

`Entry v2 → UnityAgent Control Plane → ToolBroker → fixed Unity Editor provider → Scene/Material/Script → compile → Editor PlayMode → Evidence`

This is a fixed validation capability, not arbitrary command/script execution, and does not claim Player or target-device verification.

## Marketplace boundary

The Codex Marketplace contains one public entry: `unity-agent`.

SubAgents are selected behind UnityAgent through the Resolver / Catalog contract. Standalone Artist / Graphics / WorldCreator / Performance Marketplace plugins are intentionally not published.

## Production baseline

- Unity 6.x+ + Built-in
- Unity 6.x+ + URP
- Unity 6.x+ + HDRP

Unity 2022.3 records are historical or bounded compatibility evidence, not current production support.

## Release artifacts

- `UnityAgent-UPM-0.0.8-beta.tgz`
- `UnityAgent-CodexPlugin-0.0.8-beta.zip`
- `unityagent_control_plane-0.0.8b0-py3-none-any.whl`
- `unityagent_control_plane-0.0.8b0.tar.gz`
- `UnityAgent-ArtistSubAgent-host-windows-x64-0.0.8-beta.zip`
- `UnityAgent-ArtistSubAgent-host-windows-x64-0.0.8-beta.zip.sha256`
- `UnityAgent-ArtistSubAgent-UPM-0.0.8-beta.tgz`
- `UnityAgent-SubAgent-Catalog-0.0.8-beta.yaml`
- `UnityAgent-SubAgent-Registry-0.0.8-beta.yaml`
- `UnityAgent-SubAgent-Provenance-0.0.8-beta.json`
- `SHA256SUMS.txt`

UPM:

```text
https://github.com/DarumaPPAP/UnityAgent.git?path=/Packages/com.darumappap.unity-agent#v0.0.8-beta
```

Codex Marketplace:

```powershell
codex plugin marketplace add DarumaPPAP/UnityAgent --ref v0.0.8-beta --json
codex plugin add unity-agent@unity-agent --json
```

This remains a beta release and may include breaking changes before 1.0.

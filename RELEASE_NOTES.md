# UnityAgent 0.0.8-beta

UnityAgent 0.0.8-beta promotes the current typed Control Plane and Specialist architecture into the next beta distribution.

## Entry v2 production boundary

- Typed v2 intents are the production execution entry.
- Caller-supplied src/unityagent/context identity, route, capability and runtime handoff are rejected instead of trusted.
- v1 remains an explicit validation-compatibility surface.

## Production Specialists

Consumer Catalog v3 currently exposes:

- ArtistSubAgent — `unity_cli` を通じて任意導入のArtist UPMで実行
- GraphicsSubAgent — providerless reasoning / read-only analysis
- WorldCreatorSubAgent — providerless reasoning / planning-only
- PerformanceSubAgent — providerless reasoning / read-only analysis

Reasoning specialists execute through UnityAgent's CodexRunner contract and do not use fake semantic providers.

## Hub contract alignment

- Hub Snapshot v3 / Manifest v5 are accepted through the Offline Import Gate.
- Hub registration is not treated as runtime installation, compatibility, project binding, eligibility or readiness.
- UnitySubAgentHub and individual SubAgents do not publish independent releases.
- SubAgent定義、Control Plane wheel、UnityAgent UPM、Artist UPMは同じUnityAgent checkoutから生成します。 Release provenance records `unity_agent_commit`; the old Hub pin is historical compatibility data only.
- Artist UPMとconsumer-neutral Hub Snapshotの生成元Commitを記録します。独立Artist Hostのビルド・インストール・配布は不要です。

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

## Co-located execution cutover

- Python wheel/sdist include `subagent/` definitions, instructions and contracts with resource hashes.
- Entry v2 accepts an optional canonical `requested_subagent`; incompatible ownership and unavailable activation fail closed.
- Control Plane records Adaptive Fast/Standard selection without creating extra agents or worktrees for inspection.
- OS-owned Project leases serialize cooperating Control Plane runs through execution and Evidence persistence.
- Multi-task execution, device queues and mutating specialist E2E are not yet enabled; real Editor/console observations remain separate from host validation.

## Release qualification and G1 status

- Beta release requires G0 contracts plus Unity 6.3 LTS P9 Editor evidence for the exact release commit.
- P9 evidence does **not** verify the Blender → FBX → Unity → QA → rollback production workflow.
- G1 remains `BLOCKED_NOT_RUN` until separate, independent Private CI approvals and all nine gates are observed.
- Unverified Production E2E capabilities must not be advertised or automatically enabled as verified production functionality.

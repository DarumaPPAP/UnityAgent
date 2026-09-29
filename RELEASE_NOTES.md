# UnityAgent 0.0.8-beta

UnityAgent 0.0.8-beta updates the Control Plane to the current Specialist architecture and Unity 6+ production baseline.

## Highlights

- Entry v2 typed intents are the production execution entry; v1 remains validation compatibility only.
- GraphicsSubAgent, WorldCreatorSubAgent and PerformanceSubAgent run as providerless reasoning specialists through CodexRunner.
- ArtistSubAgent remains provider-backed through `unity_artist_cli`, with the backend release pinned independently.
- The fixed Full E2E probe validates Codex/host entry → UnityAgent → ToolBroker → Unity Editor execution with evidence.
- Consumer Catalog v3 / Hub Manifest v5 / Snapshot v3 contracts are aligned.
- Current production support is Unity 6.x+ across Built-in, URP and HDRP.

## ArtistSubAgent backend

The canonical Unity package ID is now:

```text
com.darumappap.artist-subagent
```

The previous beta ID `com.darumappap.unity-artist` is not treated as the current package. Existing projects using it must migrate the dependency explicitly.

UnityAgent v0.0.8-beta pins the Artist backend to `UnitySubAgentHub@v0.0.2-beta`.

## Codex Marketplace

The Codex Marketplace contains only the `unity-agent` plugin. Specialist SubAgents are resolved inside UnityAgent and are not published as standalone Marketplace plugins.

```powershell
codex plugin marketplace add DarumaPPAP/UnityAgent --ref v0.0.8-beta --json
codex plugin add unity-agent@unity-agent --json
```

## Release artifacts

- `UnityAgent-UPM-0.0.8-beta.tgz`
- `UnityAgent-CodexPlugin-0.0.8-beta.zip`
- `unityagent_control_plane-0.0.8b0-py3-none-any.whl`
- `unityagent_control_plane-0.0.8b0.tar.gz`
- `SHA256SUMS.txt`

UPM Git URL:

```text
https://github.com/DarumaPPAP/UnityAgent.git?path=/Packages/com.darumappap.unity-agent#v0.0.8-beta
```

This remains a beta release and may include breaking changes before 1.0.

# ArtistSubAgent boundary

## Canonical identity

`ArtistSubAgent` is the Unity visual-art / cinematic specialist. Its canonical runtime identity is `artist_subagent`.

`unity_artist_cli` is not a SubAgent. It is the current backend Provider id used by ArtistSubAgent to reach the bounded Artist execution surface.

## Ownership

UnityAgent owns semantic intent, Policy, Approval, Mutation Scope, SubAgent selection, loop/retry control and durable Evidence.

ArtistSubAgent owns specialist reasoning and bounded visual-art / cinematic workflows. It does not own global routing, Policy, approval or persistence.

The backend owns execution only.

```text
User / Codex
    |
    v
UnityAgent Control Plane
    |
    v
CapabilityRequest
    |
    v
ArtistSubAgent eligibility + plan
    |
    v
Backend Provider Resolver
    |
    +-- unity_artist_cli (current compatibility backend)
    +-- future bounded backend
    |
    v
ProviderResult -> Evidence
```

## Optional installation

ArtistSubAgent is optional. Registration in a catalog does not make it available.

Before ArtistSubAgent can participate, every activation requirement in `Runtime/ReferenceImplementation/subagent-catalog.yaml` must be observed true. The current profile requires backend availability, an observed compatible support tier/backend, project binding, the Artist package and Pipeline reachability.

False or unknown requirements exclude ArtistSubAgent before execution. UnityAgent must not auto-install a missing SubAgent just to satisfy a CapabilityRequest.

## Codex surface

UnityAgent is the single Codex plugin entry. ArtistSubAgent is not distributed as an independent Codex plugin because it cannot bypass or replace UnityAgent orchestration.

Repository/plugin skills may describe how UnityAgent routes to ArtistSubAgent, but they must not duplicate the SubAgent capability contract or redefine its authority.

## Compatibility

The `unity_artist_cli` id and existing `unity-artist` executable/package names remain as backend compatibility names until a separate backend migration is intentionally performed. They must not be used as the semantic SubAgent name in new architecture contracts.

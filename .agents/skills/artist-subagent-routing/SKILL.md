---
name: artist-subagent-routing
description: Route visual-art and cinematic specialist work through the optional ArtistSubAgent without confusing SubAgent identity with its backend provider.
---

# ArtistSubAgent routing

ArtistSubAgent is the specialist identity. `unity_artist_cli` is only its current execution backend and must not be used as the semantic agent identity.

## Resolution

1. Build a provider-independent CapabilityRequest from user intent.
2. Resolve the matching SubAgent profile from `Runtime/ReferenceImplementation/subagent-catalog.yaml`.
3. Check the profile activation contract before planning or dispatch.
4. If any required environment fact is false or unknown, treat ArtistSubAgent as unavailable and exclude it. Do not auto-install it.
5. Only after the SubAgent is eligible may Runtime resolve `profile.provider_id` as the backend Provider.
6. Keep Approval, Mutation Scope, Evidence and retry ownership in UnityAgent.

The canonical relationship is:

`CapabilityRequest -> ArtistSubAgent eligibility -> SubAgent plan -> Backend Provider Resolver -> ProviderResult -> Evidence`

For ArtistSubAgent the current backend compatibility id is `unity_artist_cli`. Generic project, hierarchy, compile, test, build, play/stop, log, UI, Audio and Addressables work remains outside ArtistSubAgent.

## Invariants

- `profile_id=artist_subagent` is the specialist identity.
- `provider_id=unity_artist_cli` is an implementation detail of the current backend.
- Uninstalled, unbound, incompatible or unobservable ArtistSubAgent is not rankable.
- Missing activation facts never become success.
- Runtime never auto-installs ArtistSubAgent to satisfy a request.
- There is no separately installed Artist Codex plugin; the UnityAgent plugin owns the entry workflow.
- UI / Codex never bypasses UnityAgent to invoke the backend directly.

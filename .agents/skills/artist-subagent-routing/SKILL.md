---
name: artist-subagent-routing
description: Use when a Unity visual-art, lookdev, lighting, environment, camera, capture, evaluation, refinement, Timeline, or cinematic task needs specialist planning through the optional ArtistSubAgent.
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

## Output Contract

- State the semantic Capability and qualifiers used for SubAgent resolution.
- Report `profile_id=artist_subagent`; report backend `provider_id=unity_artist_cli` only after eligibility succeeds.
- Include the observed activation facts and their evidence.
- For mutations, report the UnityAgent approval, scope and revision requirements, result, and Evidence references.
- If unavailable, identify the false or unknown activation fact and do not claim execution.

## Checklist

- [ ] The request matches the ArtistSubAgent profile's declared scope.
- [ ] Every activation fact is checked against the observed environment and project binding.
- [ ] Missing, unbound, incompatible, or unobservable specialists are excluded without installation.
- [ ] Backend Provider resolution happens only after SubAgent eligibility; UnityAgent retains control and approval.
- [ ] A Provider result is not presented as proof of Editor, Player, or human visual acceptance.

## Common Mistakes

- Using `unity_artist_cli` as the specialist identity instead of the backend ID.
- Treating a catalog entry as proof that ArtistSubAgent is installed, compatible, bound, or reachable.
- Treating an unknown activation fact as true or installing a missing SubAgent to satisfy a request.
- Calling the backend directly from Unity UI, Codex, or a task graph.
- Routing generic project, hierarchy, compile, test, build, UI, Audio, or Addressables work to ArtistSubAgent.
- Claiming Editor, Player, or visual acceptance from a successful CLI envelope alone.

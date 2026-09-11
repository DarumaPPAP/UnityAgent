---
name: unity-artist-cli-routing
description: Use when routing Unity visual-art or cinematic work through UnityArtistCLI and the existing UnityAgent Provider runtime.
---

# UnityArtistCLI routing

Use semantic capability and qualifier requests, not Provider names, in task graphs. UnityAgent remains the Architect, Commander, and Loop Owner; UnityArtistCLI is the specialist Provider.

```yaml
capability: domain.workflow
qualifiers:
  domain: visual_art
  workflow: lookdev_refine
operation_kind: mutate
required_evidence:
  - visual_direction_plan
  - exact_diff
  - expected_revision
```

The authoritative path is `CapabilityRequest -> Runtime Guard -> ToolBroker -> Resolver -> Environment Snapshot -> Provider Registry -> Dispatcher -> Provider Adapter -> ProviderResult -> Evidence Normalizer -> Persistence`.

The Provider is selectable only when project binding, UnityArtistCLI availability, package installation, Pipeline reachability, qualifier compatibility, and evidence requirements are observed. Generic Unity project, hierarchy, GameObject, compile, test, build, play/stop, log, UI, Audio, and Addressables work stays delegated to the official Unity CLI or existing Providers.

Mutation requires an exact plan, expected revision, and UnityAgent approval token. Apply registers Undo, does not save automatically, and must preserve exact diff, before/after capture, Timeline evidence, and human evaluation status without claiming unobserved Editor results.

## Output contract

- Semantic capability and qualifiers used for routing
- Selected Provider and observed availability evidence
- Approval / revision requirements for mutation
- ProviderResult and normalized Evidence references
- Explicitly unverified or unavailable Editor / Player / visual claims

## Checklist

- [ ] Graph uses semantic capability/qualifiers rather than a Provider product name
- [ ] UnityAgent owns routing, policy, approval, and loop state
- [ ] UnityArtistCLI is selected only from observed compatibility and availability
- [ ] Generic Unity work stays with the official Unity CLI or existing Provider
- [ ] Mutation has exact diff, expected revision, approval, Undo, and Evidence
- [ ] Missing visual or Editor evidence is not reported as verified

## Common mistakes

- Encoding `unity-artist` as the canonical Graph node instead of `domain.workflow` / qualifiers.
- Calling UnityArtistCLI directly from Unity UI or the Codex entry surface.
- Routing compile, build, hierarchy, or ordinary GameObject operations to the artist Provider.
- Applying a visual mutation without expected revision or approval.
- Treating a successful CLI envelope as proof that Editor, Player, or human visual acceptance passed.

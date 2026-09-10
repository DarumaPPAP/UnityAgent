---
name: unity-agent-provider-routing
description: Route visual-art and cinematic capabilities to UnityArtistCLI through the existing provider runtime.
---

# UnityAgent provider routing

Use semantic capability and qualifier requests, not provider names in the task graph.

```yaml
capability: domain.workflow
qualifiers:
  domain: visual_art
  workflow: lookdev_refine
project_root: D:/Projects/MyGame
operation_kind: mutate
required_evidence:
  - visual_direction_plan
  - mutation_evidence
```

The existing path is authoritative:

`CapabilityRequest -> Runtime Guard -> ToolBroker -> Resolver -> Environment Snapshot -> Provider Registry -> Dispatcher -> Provider Adapter -> ProviderResult -> Evidence Normalizer -> Persistence`

The `unity_artist_cli` provider is selected only when its environment facts, supported qualifiers, project binding and evidence contract match. The former `myunitymcp` provider remains a legacy migration reference and is not production-enabled or higher priority.

Artist-specific work includes lookdev, lighting, environment, camera, capture, evaluation, refinement and cinematic Timeline workflows. Generic project, hierarchy, GameObject, compile, test, build, play/stop, logs and screenshots remain delegated to the general Unity CLI or existing providers.

Mutation requests require an exact plan, expected revision and approval token. Preserve before/after capture, exact diff, timeline evidence and final evaluation in the durable evidence record.

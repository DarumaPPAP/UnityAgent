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

## Setup and status contract

UnityAgent is the Control Plane. SubAgents and their backends are optional capabilities; their availability is reported at the capability or product boundary where it was observed.

`setup doctor` is observational and never installs a product. Its request `products` list names the products to inspect; the request has no global `required` flag. Capability optionality remains defined by the catalog/profile, and a missing product does not make an otherwise successful observation fail:

| Layer | Meaning |
| --- | --- |
| Installer Provider `status: passed` | All requested observations completed and returned recognized product states. It does not mean every product is installed. |
| Installer Provider `status: failed` | An observation failed to execute or returned an invalid state. Failure details remain on the affected entry. |
| Product entry `status: verified` / `installed` | That product was observed available. |
| Product entry `status: unavailable` | That product was observed missing or unavailable; keep its `reason` and `message`. This must not be rewritten as `verified`. |
| Product entry `status: stale` | The product was observed, but its version is incompatible; keep it distinct from both `unavailable` and execution failure. |
| Control Plane `status: completed` | Resolution, provider operation, and evidence handling completed successfully. |
| Control Plane `status: blocked` | The request could not complete because resolution or provider execution failed. |
| CLI exit code | `0` means the Control Plane operation completed; nonzero means the operation failed or was blocked. It does not encode each product's availability. |

The Unity Setup Window's doctor summary follows the structured Control Plane response, shows management-resolution/provider failure reasons, and shows product entries independently. It may report `UnityAgent: Ready` alongside `Artist CLI (backend): Unavailable`; that does not claim ArtistSubAgent is available. Capability resolution remains authoritative for capability availability.

Doctor Evidence records the diagnostic operation status. The canonical hash covers the provider result, including each product status and its unavailable reason; Evidence must not rewrite an unavailable product as verified.

`plan` and `apply` keep their action and approval boundary. A missing product may appear in a plan as an install action that requires approval; plan generation does not install it. `apply` requires a matching approved plan and approval reference. Unavailable products that are not in the requested plan do not become dependencies of that plan.

Capability resolution is separate from Installer Provider observations. False, unknown, unavailable, or non-compatible Artist requirements exclude the Artist provider candidate only. Resolution for independent requests, such as `project.inspect`, continues through its own eligible provider. An execution exception is `failed`, not `unavailable`, and remains a failure for the affected operation.

## Codex surface

UnityAgent is the single Codex plugin entry. ArtistSubAgent is not distributed as an independent Codex plugin because it cannot bypass or replace UnityAgent orchestration.

Repository/plugin skills may describe how UnityAgent routes to ArtistSubAgent, but they must not duplicate the SubAgent capability contract or redefine its authority.

## Compatibility

The `unity_artist_cli` id and existing `unity-artist` executable/package names remain as backend compatibility names until a separate backend migration is intentionally performed. They must not be used as the semantic SubAgent name in new architecture contracts.

## Offline Catalog Import Gate

`UnitySubAgentHub` exports the existing `SubAgentProfileCatalog` wire shape as a data-only Snapshot. UnityAgent accepts that Snapshot only as an explicit Offline input:

```text
Snapshot bytes + source_ref + expected SHA-256
        |
        v
Strict schema / identity / capability / Provider / activation / scope / approval / Evidence checks
        |
        v
Added / Removed / Changed / No-op Import Plan
```

`python Tools/import_subagent_catalog.py` is read-only. It does not download the Hub Artifact, observe the current Project, install a SubAgent, hot-reload the Runtime catalog, or write `Runtime/ReferenceImplementation/subagent-catalog.yaml`. A non-no-op update remains a reviewed Git change; protected Field changes, deletions, default-profile changes, and provenance changes are blocked in the plan.

The checked-in UnityAgent catalog and ReferenceImplementation durable Evidence currently use `UnityAgent.ReferenceImplementation.v1.1`. A Snapshot carrying `UnityAgent.ReferenceImplementation.v1` is reported as an evidence-producer protected-field mismatch; the Gate never normalizes it. The existing `runtime_profile_revision` fingerprint now covers both `Runtime/Tooling/provider_registry.yaml` and the SubAgent catalog, so Resume continues to apply the existing in-flight-action block and Evidence keeps its existing profile binding digest.

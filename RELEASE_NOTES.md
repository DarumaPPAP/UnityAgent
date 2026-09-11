# UnityAgent 0.0.1-beta

UnityAgent 0.0.1-beta is the first beta release of the five-layer Unity automation architecture centered on a single UnityAgent Control Plane.

## Production surface

- UnityAgent remains the Architect / Commander / Loop Owner.
- Unity UI and the Codex `unity-agent` plugin are entry surfaces only; they do not route directly to Providers.
- Capability requests flow through Runtime Guard, ToolBroker, Resolver, Provider Registry, Dispatcher, Provider Adapter, ProviderResult, and Evidence normalization.
- Official Unity CLI remains the first provider for supported project/editor/pipeline operations.
- UnityArtistCLI is integrated as the specialist provider for visual art and cinematic workflows.
- Setup and mutation remain approval-gated and fail closed when required evidence is unavailable.

## Distribution

This release publishes the following artifacts from the same immutable tag:

- UnityAgent UPM package (`com.darumappap.unity-agent`)
- Codex `unity-agent` plugin archive
- Python Control Plane wheel and source distribution
- SHA-256 checksums for every published artifact

The bundled marketplace pins UnityArtistCLI to `v0.0.1-beta` so this UnityAgent beta remains reproducible instead of following the moving `main` branch.

## Verification status

The merged migration passed the repository's canonical validation, runtime harness, persistence, policy/context, operations, eval, orchestration, production smoke, and production tool runtime checks. A live Unity 6000.6.0f1 Built-in route was exercised through UnityAgent -> UnityArtistCLI -> official Unity command -> Pipeline -> Editor.

## Beta limitations

- This is a beta contract and breaking changes are still possible before GA.
- UnityAgent-level live provider E2E coverage for Unity 6 URP/HDRP is not yet complete.
- Unity 2022.3 completion remains dependent on compatible official Pipeline behavior; blocked rows must stay fail-closed rather than silently selecting an unapproved backend.
- Release signing is not yet a GA-grade trust mechanism; beta artifacts are published with SHA-256 checksums.

## Version contract

The canonical release version is `0.0.1-beta`. UPM and Codex plugin manifests use that exact value. The Python package uses the PEP 440 equivalent `0.0.1b0`.

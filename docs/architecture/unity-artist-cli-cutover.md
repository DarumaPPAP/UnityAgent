# Legacy UnityArtistCLI cutover note

This document described the intermediate migration where `unity_artist_cli` was treated as the specialist identity.

That model is no longer canonical.

See [ArtistSubAgent boundary](artist-subagent-boundary.md) for the current contract:

- `ArtistSubAgent` / `artist_subagent` = specialist identity.
- `unity_artist_cli` = current backend Provider compatibility id.
- ArtistSubAgent is optional and is excluded when its activation requirements are not observed true.
- `unity_artist_cli.compatible` is derived from support metadata; missing support facts remain unknown and block resolution.
- UnityAgent does not auto-install a missing SubAgent to satisfy a CapabilityRequest.
- UnityAgent remains the single Codex plugin entry and orchestration authority.

Historical implementation details remain available in Git history and decision logs. Do not copy the old Provider-as-SubAgent model into new code.

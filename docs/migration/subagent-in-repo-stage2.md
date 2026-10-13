# SubAgent migration — Stage 2: Artist Backend source

Co-located the original Artist optional Unity Package as
\`Packages/com.darumappap.artist-subagent/\` and the Artist CLI as
\`cli/artist/\`, preserving all published .meta GUIDs, asmdefs, source and CLI executable name.

The canonical Artist static semantic authority is \`subagent/artist_subagent/manifest.yaml\`.
\`tools/validate_artist_product_identity.py\` enforces aligned package/CLI identity,
manifest version, preserved asset metadata and optional installation.

The separate GitHub Hub source and old distribution path have not yet been retired.
**A UPM Git subpackage exposes only its own package folder**; the UnityAgent UPM does
not expose root-level \`cli/artist/\` or \`subagent/\` simply because they share a repository.
An explicit packaging and managed setup/install cutover must be validated before the
pinned Hub can safely be removed. No current real-Editor/console evidence is claimed.

Historical Unity 2022.3 CLI test fixtures remain regression-only, not supported runtime targets.

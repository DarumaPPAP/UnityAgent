# Preserved Artist projects

`artist-e2e/` is the unchanged 6000.6.0f1 Artist verification project with Unity Pipeline 0.6.0-exp.1. `historical/2022.3/` retains the historical bounded fallback fixture; it is not current support. Migration changes only the relative local Artist package dependency to account for the new depth. The imported P9 source commit and the source-file inventory are recorded in [P9 migration provenance](../../../ci/P9-MIGRATION-PROVENANCE.json).

The READMEs inside these preserved projects describe their original sessions. Their old `Tests/Compatibility/` paths refer to [archived records](../evidence/artist/historical/index.json), never to current successful runs. Original URP/HDRP projects referenced by those records were absent from the baseline. Current licensed Editor, Pipeline, capture and visual validation is `BLOCKED_NOT_RUN` / `not_observed`.

The preserved 6000.6 package lock also updates only the local Artist file dependency depth to match its relocated manifest; all external package version/dependency observations remain unchanged.

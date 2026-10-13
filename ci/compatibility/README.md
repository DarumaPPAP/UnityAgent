# Artist compatibility contracts

`support-matrix.yaml` is the single declared Unity 6.x+ Built-in / URP / HDRP support matrix. It declares product targets, rather than measured Editor success. Unity 2022.3 is excluded from current production support.

All previously checked-in session, release audit, and production acceptance records are archived byte-for-byte under [historical evidence](../evidence/artist/historical/). Their [preservation index](../evidence/artist/historical/index.json) records original paths and SHA-256 values, and classifies each as historical with current observation `not_observed`. Embedded paths and original `passed` fields remain historical facts. Original URP/HDRP fixture paths were absent from the baseline checkout; those records cannot prove a current fixture or current successful run.

[Archive validators](../verify/) check the preserved historical shape and hashes. They do not run Unity. Current Editor / Pipeline / capture / visual validation remains `BLOCKED_NOT_RUN`. New measured evidence belongs under `ci/evidence/artist/current/` only after a licensed Editor run supplies exact versions, logs, results, and artifacts.

The canonical [6000.6 Artist E2E project](../unity-projects/artist-e2e/) preserves its scenes and resources. The [2022.3 project](../unity-projects/historical/2022.3/) is historical only. A disposable live check requires an explicitly targeted, licensed, connected Editor:

```powershell
python cli/artist/scripts/run_minimal_live_smoke.py --project-path .\ci\unity-projects\artist-e2e
.\cli\artist\scripts\verify-external-cli.ps1 -ProjectPath .\ci\unity-projects\artist-e2e
```

These mutation-capable checks are separate from host contracts and have not run during consolidation. UnityAgent must independently observe every manifest activation gate; archive integrity and Hub registration do not establish runtime readiness.

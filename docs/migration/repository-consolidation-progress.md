# Repository Consolidation Progress

| Phase | Verified result | PR / merge |
|---|---|---|
| P0 Agent | Complete | #173 / 007dbc66365a8c2ca26fa12cbc89d5b544d7339a |
| P0 Hub | Complete | #93 / 83dcd6e7a2cba94e5bc0b4975579252da1d5e69a |
| P1 Agent | Canonical Green, Squash Merge | #175 / 0138030ac5b54ed45e8c5b0892f4170f48290184 |
| P2 Hub | Hub/Artist/Branch CI Green, Squash Merge | #94 / ccd6a21dee753c60211c1aa947f5220366cd7229 |
| P3 Agent | Hub pin and Release/Artist transition prepared; local validation recorded below | chore/repository-consolidation-p3 |
| P4 Hub | Artist/compatibility/docs move in progress; merge after P3 | chore/repository-consolidation-p4 |
| P5–P6 Agent | src/wheel/caller migration in isolated worktree | chore/repository-consolidation-p5 |
| P7 Hub | CI foundation prepared in isolated worktree; integrate after P4 | chore/repository-consolidation-p7 |
| P8 | Pending final layout and audit | — |

Source Lock now pins Hub merged full SHA ccd6a21dee753c60211c1aa947f5220366cd7229, Hub/Tools/export_snapshot.py, Hub/Registry and Hub/SubAgents. Artist CLI remains src/UnityArtist.Cli until the producer move. Release resolves exact allowlisted source paths from the same lock; old/new Artist layouts are prepared BEFORE producer migration. Mixed Catalog layouts, wrong repository/full SHA/identity and unknown CLI project remain rejected. New source-layout tests RED→GREEN, actual Development/Pinned Snapshot both read-only no_op.

P0 Inventory stays immutable historical evidence. Execution-file blocker resolved via Agent #174. Unity Editor/License/Player/Visual/device remain BLOCKED_NOT_RUN. Next: P3 CI Green/Squash Merge, Hub Artist move and final Agent re-pin. Confirm GitHub reality before resuming.

## P4 Artist producer and Source Lock (2026-10-10)

Hub #95 merged with all required and Artist host checks Green at `547007b11545d445d9e99a97c41a3d6f0a055d03`. Artist CLI project now resolves to `cli/artist/UnityArtist.Cli.csproj`; static verifiers resolve to `ci/verify`. This Agent change re-pins that full immutable SHA after consumer compatibility #176. Actual Development/Pinned imports both remain read-only `no_op`; Canonical validation passed locally. PR and required CI verification precede merge. P5/P6 implementation is separately under verification; P7/P8 are not yet merged. Editor/License/visual/device gates remain `BLOCKED_NOT_RUN`.

## P5 / Agent P6 implementation worktree

- Branch: `chore/repository-consolidation-p5`, based on P1 implementation `b200c6f`.
- Product namespace, CLI, resources, repository tools/eval/tests and owning docs migrated;
  exact map and decisions: `docs/migration/python-src-migration.md` and
  `docs/migration/python-src-path-map.json`.
- Latest P4 Source Lock was integrated on the owning branch; it pins Hub
  `547007b11545d445d9e99a97c41a3d6f0a055d03` with the new Artist project path.
- Canonical validation PASS: 28 validators, graph check, original 10 suites plus
  packaging and nested reference suite; 622 tests, one Windows-specific skip.
- Additional root discovery 23 tests PASS and ProductionSmoke contract 11 tests PASS.
- Build sdist/wheel and clean installed-wheel proof PASS outside checkout, including
  doctor (unavailable external tools reported honestly), policy/catalog/context loads,
  resource SHA-256 manifest, complete fingerprints and specialist schema bindings.
- UPM npm pack PASS (23 archive entries); all original UPM .meta/GUID bytes and
  VERSION/UPM/Plugin/Python mirrors unchanged.
- Fresh review fixes: authored-root capability foundation (temporary mutation regression
  RED→GREEN), exact original-case path-map keys, VERSION resource inclusion, and
  host-state GoldenTaskRunner default (RED→GREEN).
- Local PowerShell/Windows specialist execution, Unity Editor/license/Player/Visual:
  BLOCKED_NOT_RUN. Parent owns PR/merge, latest lock integration and P8 layout enforcement.

- Full local evidence: `/workspace/p5-logs/canonical-verified.log`,
  `editable-clean.log`, `build-complete.log`, `wheel-proof-complete.log`,
  `root-tests.log`, and `production-smoke-contract-second.log`.
  Earlier failure logs remain alongside these; `canonical-complete.log` records an
  invalid concurrent resource regeneration run, superseded by the sequential run.
- Built artifacts: `dist/unityagent_control_plane-0.0.8b0-py3-none-any.whl` and
  `.tar.gz`; wheel contains 228 verified resource hashes and no repository validators.


P5 integration rebased onto verified P4 Agent main `ef6b409fab5ec5fde89ea291df1a72bb2c468f10`. P3's source-path resolver and tests were relocated into tools/tests; Release uses the validated resolver. Live camera and final-gate repository helpers now use the consolidated Hub Artist project/verifier paths and UnitySubAgentHub default checkout. Their restore-before-publish regression passed; the integrated full Canonical validation passed. Actual Development/Pinned imports remain read-only no_op. This is implementation/host verification; live Windows/Unity/visual execution remains BLOCKED_NOT_RUN.

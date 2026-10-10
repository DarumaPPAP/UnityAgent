# Repository Consolidation — final Agent implementation audit

P1–P8 cloud-executable implementation is consolidated in this final Agent PR. [Execution ledger](repository-consolidation-progress.md) records the verified producer/consumer PRs and merge SHAs; this PR must pass the unchanged required Canonical Validation before merge. Immutable baseline sections below remain historical, not current completion claims.

Final authored directory roots: `.agents/`, `.github/`, `src/`, `Packages/`, `tests/`, `eval/`, `tools/`, `docs/`, `scripts/`. Only necessary root configuration files exist. Optional `.devcontainer` is allowed without creating it; no empty ci directory was invented. `repository-layout.json` owns paths; `src/unityagent/contracts/repository-authority-map.yaml` separately owns domain authority. Strict all-PR layout validation rejects old roots and unknown roots, prohibited directories, missing/escaping canonical paths and external/dangling authored symlinks.

| Baseline owner | Final owner |
|---|---|
| Context / ControlPlane / Operations / Orchestration / Persistence / Policy / Runtime | src/unityagent lowercase product namespaces |
| Product CLI formerly Tools/unity_agent_cli.py | src/unityagent/cli.py, unity-agent = unityagent.cli:main |
| Tools / distributed layer Tests / Eval | tools / tests/domain / eval |
| Specs | machine contracts in product contracts, human documents in docs/architecture/specifications |
| SkillReferences / Templates | docs/standards and docs/templates or owning skill references |
| Duplicate Prompt copies | callers use src/unityagent/context/prompt/templates; duplicates deleted |
| Hub Registry/Schemas/SubAgents | Hub/Registry, Hub/Schemas, Hub/SubAgents |
| Hub validators/tests / Artist CLI | Hub/Tools, Hub/Tests / cli/artist |
| Hub compatibility, project, measured records and frozen Legacy | ci/compatibility, ci/unity-projects, ci/evidence/artist/historical, tests/fixtures/legacy |

Exact Agent551 source map: [python-src-path-map.json](python-src-path-map.json), [implementation decisions](python-src-migration.md). Hub117 map and historical hash indexes remain in its docs/migration/consolidation. No old authored Agent/Hub root remains. Product imports use unityagent.*; repository-only validators are outside the product. Runtime definitions are copied from one authored source at build, and installed resources never search for a checkout. Fresh installed-wheel verification exercises228 SHA-256 resources, help/doctor, policy/catalog/context commands, fingerprints and specialist schemas outside checkout. Resource copying is a generated distribution artifact, not a second authored authority.

Final Hub source is immutable mergeSHA 17e60ce820164efc2cea59c415d29717ac6f103c with Hub/Tools/export_snapshot.py, Hub/Registry/subagents.yaml, Hub/SubAgents/artist_subagent/manifest.yaml and cli/artist/UnityArtist.Cli.csproj. Both actual committed Development/Pinned imports return read-only no_op and snapshot SHA-256 ac62220716ac087327228dfc58e1d10db7dc7e438e1407e865d2d752242499a8. Consumer compatibility landed before each producer move; no unknown path/repository/identity/hash fallback was added.

Capability, Provider, Profile, Policy/Approval/Evidence, optional-install/auto_install=false and public UPM IDs are preserved. All23 Agent UPM files retain baseline bytes, including .meta/GUID. Hub package code/meta/identity retains baseline bytes; its README paths changed. Frozen Legacy inventory77 tools and tagv1.1.1 object f74d6f86f65178492aee1eaac5c01acb7ba5514a remain unchanged. P0 inventories and historical evidence retain their original hashes. The orphan Hub specification meta was deleted only after GUID dependency search.

Intentional old-path references: immutable P0 inventories/reports, migration maps and historical evidence; v1/v2/v3 source fixtures; strict old/new Hub source compatibility; Runtime/CodexRunner producer IDs and the Context Explorer schema $id (wire identifiers, not filesystem dependencies); preserved Unity menu labels and installer host-state directories; external DarumaPPAP/MyUnityMCP specification references (owned by that separate historical repository); external Unity SRP package-internal Runtime paths. The active Artist external spec now points to Hub docs/architecture/artist-subagent-spec.md. EnvironmentSnapshot.myunitymcp remains a public observation field used by schema/probes/consumers; no retired Runtime adapter/Legacy50PORT was restored. Remove compatibility only through an explicit versioned consumer migration.

Unity6000.6 full/minimal,6000.3.12f1 minimal, Built-in/URP/HDRP camera readback fixtures and dynamic next-stream Canary are implemented in Hub. Host/static PASS does not establish Editor compatibility. Actual Unity Editor/license, graphics/pipeline, Player/device and Windows Named Pipe remain BLOCKED_NOT_RUN. Hub run38066203244 uploaded blocked canonical/minimal evidence; IDs11674463178/11675213275/11674293315, expire2026-10-24. Cloud official Editor/UPM metadata calls returned proxy403. Provisioned replay commands, exact scopes and artifact requirements: Hub docs/migration/unity-ci-foundation.md. Artifact expiry never converts blocked evidence into PASS.

No main direct push, force push, Release/tag publication, policy relaxation or new prohibited directory occurred. Actual final mergeSHAs are available through the phase PRs; a commit cannot include its own eventual squashSHA. The workspace final audit records both final mainSHAs after merge.

---

# Repository Consolidation P0 Audit

## Scope and authority

User request: implement P0–P8 across DarumaPPAP/UnityAgent and DarumaPPAP/UnitySubAgentHub, verify each phase in a PR, then squash merge after required checks succeed. No direct main push, release/tag publication, new backends directory, policy relaxation, or automatic specialist installation.

Implementation specification: UnityAgent_Repository_Consolidation_Spec_v1.md, SHA-256 `fb4744860b5fc0f44f01d1c31db8df867c789ea8dccdef983a3728d797174cee`. The two received attachments have identical bytes. The execution Goal was subsequently fetched directly from UnityAgent main; see the final execution ledger above. Current explicit user instructions take precedence over general skill approval handoffs.

Historical baseline paths in this report and inventory are deliberately preserved for migration comparison. They are not declarations of the final layout. Inventory is not a replacement for repository authority or future layout contracts.

## Immutable baseline

| Repository | Latest main at preflight |
|---|---|
| UnityAgent | `1dc42590843d0373440306e1b93e9764a857be36` |
| UnitySubAgentHub | `aa6275c8673fa7a38d5d6a8aabbef5507ee96ad1` |
| Pinned Hub Source Lock | `61d3fad2e0aef50b69fc76fbbd839aca076de19f` |
| First reference: hatayama/unity-cli-loop | `b04b58e8c94c6b71808a5b29e65cc41e361ded19` |
| MyUnityMCP immutable v1.1.1 target | `f74d6f86f65178492aee1eaac5c01acb7ba5514a` |

Fetch and push dry-run succeeded for both repositories through the configured proxy; dry-run created no branch. Connector metadata reports admin/maintain/push/pull. The branch-protection endpoint returned 403 Resource not accessible by integration. Public Ruleset endpoints succeeded: both repositories forbid deletion/non-fast-forward on main, require linear history and a pull request, permit squash only, require resolved threads, and have no bypass actors. Never interpret the inaccessible legacy endpoint as absent protection.

Required checks: UnityAgent `Canonical Validation`; Hub `Validate Branch Name` and `Validate registry, manifests, and snapshot contract`. Workflow-level PR path filters are absent from these required jobs. Artist host contract is separately path-triggered. No ruleset or required check was modified.

## Contract and source audit

AGENTS.md, User/Approval/Evidence src/unityagent/policy, branch policy, repository authority maps, Source Lock, and current workflows were read. UnityAgent is the sole Control Plane; Hub is static metadata. Profile ID / provider ID separation, optional required=false/auto_install=false specialists, fail-closed activation, hashes/provenance, UPM names and asset GUIDs remain protected.

Route: architecture-design, using current-call Context Assembly; this route declares no required_policy_clauses. User, Approval and Evidence policies were additionally reviewed for this cross-repository task. The existing unrelated checkout fixture newline difference is preserved in the original checkout; worktrees isolate this audit.

Both Development and Pinned snapshots pass the existing real Consumer Import Gate as read-only `no_op`. Their commits differ but snapshot SHA-256 is `b156ee93fab5abddc8a7785c8493b835ce3111eae80394f4e42f6f59f574e6d5`; catalog_write_performed=false. Hash is byte identity evidence, not a cryptographic signature. Saved import plans are in consolidation/.

692 Agent and 199 Hub committed files are indexed with byte SHA-256, sizes, and root counts. The reference index contains 2142 Agent and 596 Hub path occurrences. Only frozen Legacy and 2022.3 fixture references are classified historical automatically; remaining entries require owning-caller review. Duplicate bytes alone never authorize removal. At P0, four Prompt files matched Context/Prompt/Templates byte-for-byte; P6 migrated callers and removed only the duplicate copies. No production file was deleted in P0.

EnvironmentSnapshot.myunitymcp remains required in the environment schema, dataclass, discovery and fixtures after adapter retirement. It is an observation/wire compatibility surface; do not remove it as a directory cleanup without consumer migration evidence.

## Differences and disposition

- Initial local checkouts lagged latest main by Agent #172 and Hub #90–#92. Fresh fetch corrected the baseline. The Consumer Gate described by the spec exists in both latest workflows; no replacement is needed.
- Artist CLI tests are a Python unittest harness exercising the .NET executable, not a separate .csproj. Preserve that actual test runner when moving under cli/artist/tests.
- Current Hub support matrix contains exactly three Unity 6.x+ family rows. This is a declared product contract, not evidence that exact versions/pipelines ran in this Cloud session.
- Canonical current Unity fixture is 6000.6.0f1 with com.unity.pipeline 0.6.0-exp.1. The 2022.3.22f1 fixture is historical. Recorded URP/HDRP paths have no corresponding current fixture; their prior evidence must not establish a fresh successful run.
- First-reference current workflows demonstrate full EditMode, a smaller 6000.5 fixture and stable PR compile jobs. This fetched upstream commit has no dynamic next-series Canary workflow. Implement the requested Canary independently with provenance rather than claim to copy an existing upstream Canary.
- The initial .NET channel installer tried a denied ci.dot.net host. The official allowed builds.dotnet.microsoft.com feed succeeded. Final host SDK is 8.0.425; no credential values were inspected or committed.

## Verification observed in this Cloud session

| Gate | Result |
|---|---|
| Agent canonical python tools/validate_all.py | PASS: 574 unittest cases across 10 suites, plus canonical validators |
| Hub authority / registry / snapshot export | PASS: 0 errors |
| Hub unittest discovery | PASS: 32 tests |
| Artist backend / Unity API / portable-path static validators | PASS |
| .NET 8 Release build | PASS: 0 warnings, 0 errors |
| Artist executable contract tests | PASS: 11 tests |
| Development and Pinned Consumer Gate | PASS: read-only no_op, immutable source refs and SHA-256 |
| Unity Editor / License / Pipeline / Player / Visual / device | BLOCKED_NOT_RUN: no configured Editor, License or device runner |

Python 3.12.14, Node 24.19.0, Git and gh are present. PowerShell is unavailable locally; existing GitHub Canonical CI supplies its installer syntax gate. A generic gh auth check made inside the network sandbox could not contact the proxy; git operations with supported sandbox escalation and connector operations are the confirmed usable paths. api.github.com is not an allowed Cloud destination; use the connected GitHub API tools rather than bypass the proxy policy.

## Resume and migration order

Preserve all P0 evidence. Receive/read the designated execution file and compare its instructions with the canonical spec and current code. Execute P1 Consumer dual-read first, then P2 Hub core move, P3 pin merged full SHA, P4 Artist consumer preparation → Hub move → final pin, P5 src packaging/wheel/installer migration, P6 caller-first cleanup/knowledge preservation, P7 version/pipeline/Canary CI, P8 layout contracts and final audits. Each phase requires green checks before squash merge. Do not disable a failing gate or replace immutable source references with HEAD/main.

P1–P8 are not implemented by this P0 audit. No code/static migration completion or Editor success is claimed.

## P1 execution-file blocker resolved

Execution Goal acquired directly from GitHub main via #174. P0 historical inventory is preserved. P1 uses exact old/new manifest references and exporter paths rather than a permissive source fallback. Reasoning contract path relocation is compared only against the Consumer-owned original identity; execution kind, runtime, required observations and contract leaf stay protected. Old source pin continues to validate.

## P3 Source Lock and P4 Consumer preparation

Pinned Hub source moves to merged P2 commit ccd6a21dee753c60211c1aa947f5220366cd7229. Release uses one validated allowlist resolver for exporter, registry, validator, test runner and Artist CLI paths. This accepts only the known old/new directory pairs, not arbitrary lock-supplied commands, and keeps package/manifest identity checks. Artist new layout is prepared before Hub producer move. Release publication was not invoked.

### P4 final Artist pin

Hub Artist/Compatibility producer #95 merged at `547007b11545d445d9e99a97c41a3d6f0a055d03` after Agent #176 installed explicit new/old path validation. Lock uses new Artist project path, Hub catalog paths and that immutable producer SHA. Real read-only Development/Pinned imports are `no_op`; no release/tag publication occurred. Subsequent final pin follows P7/P8 Hub merges.

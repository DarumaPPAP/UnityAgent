# Repository Consolidation P0 Audit

## Scope and authority

User request: implement P0–P8 across DarumaPPAP/UnityAgent and DarumaPPAP/UnitySubAgentHub, verify each phase in a PR, then squash merge after required checks succeed. No direct main push, release/tag publication, new backends directory, policy relaxation, or automatic specialist installation.

Implementation specification: UnityAgent_Repository_Consolidation_Spec_v1.md, SHA-256 `fb4744860b5fc0f44f01d1c31db8df867c789ea8dccdef983a3728d797174cee`. The two received attachments have identical bytes. The separately named execution file CodexCloud_UnityAgent_Complete_Goal.md has not yet been received; do not invent its contents. Current explicit user instructions take precedence over general skill approval handoffs.

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

AGENTS.md, User/Approval/Evidence Policy, branch policy, repository authority maps, Source Lock, and current workflows were read. UnityAgent is the sole Control Plane; Hub is static metadata. Profile ID / provider ID separation, optional required=false/auto_install=false specialists, fail-closed activation, hashes/provenance, UPM names and asset GUIDs remain protected.

Route: architecture-design, using current-call Context Assembly; this route declares no required_policy_clauses. User, Approval and Evidence policies were additionally reviewed for this cross-repository task. The existing unrelated checkout fixture newline difference is preserved in the original checkout; worktrees isolate this audit.

Both Development and Pinned snapshots pass the existing real Consumer Import Gate as read-only `no_op`. Their commits differ but snapshot SHA-256 is `b156ee93fab5abddc8a7785c8493b835ce3111eae80394f4e42f6f59f574e6d5`; catalog_write_performed=false. Hash is byte identity evidence, not a cryptographic signature. Saved import plans are in consolidation/.

692 Agent and 199 Hub committed files are indexed with byte SHA-256, sizes, and root counts. The reference index contains 2142 Agent and 596 Hub path occurrences. Only frozen Legacy and 2022.3 fixture references are classified historical automatically; remaining entries require owning-caller review. Duplicate bytes alone never authorize removal. Four Prompt files match Context/Prompt/Templates byte-for-byte; callers must migrate before removing them. No production file was deleted in P0.

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
| Agent canonical python Tools/validate_all.py | PASS: 574 unittest cases across 10 suites, plus canonical validators |
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

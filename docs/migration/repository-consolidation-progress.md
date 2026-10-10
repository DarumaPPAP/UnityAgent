# Repository Consolidation — P1–P8 execution ledger

P0 was inherited, not reimplemented. The execution Goal was fetched directly from UnityAgent main; SHA-256 76dc9cea0556a4d7c36229356cfc98c3ba93349cc88afffe149aa35ae324a4c4. Implementation spec SHA-256 fb4744860b5fc0f44f01d1c31db8df867c789ea8dccdef983a3728d797174cee; the two documents differ.

| Phase | Repository / PR | Squash merge SHA / verified result |
|---|---|---|
| P0 inherited | Agent #173 | 007dbc66365a8c2ca26fa12cbc89d5b544d7339a; required Green |
| P0 inherited | Hub #93 | 83dcd6e7a2cba94e5bc0b4975579252da1d5e69a; required Green |
| P1 Consumer first | Agent #175 | 0138030ac5b54ed45e8c5b0892f4170f48290184; Canonical Green |
| P2 Catalog producer | Hub #94 | ccd6a21dee753c60211c1aa947f5220366cd7229; required/Artist host Green |
| P3 pin + Artist consumer preparation | Agent #176 | 66463f54b92178a830a746b8d24e3cbe7d729605; Canonical Green |
| P4 Artist/compatibility/history producer | Hub #95 | 547007b11545d445d9e99a97c41a3d6f0a055d03; required/Artist host Green |
| P4 producer re-pin | Agent #177 | ef6b409fab5ec5fde89ea291df1a72bb2c468f10; Canonical Green |
| P5–P6 src/wheel/caller cleanup | Agent #178 | 9b6026257a2bf5cdb9e6aed367caea52f2d72731; Canonical Green run38086435124 |
| P7 version/pipeline/Canary CI | Hub #96 | a042bf72c74ec9aa0004d5b2e12d6b7726cf4bf6; required/Artist/compatibility host Green |
| P8 Hub layout | Hub #97 | 7c67f71c7eebd38ca7d24d3bf9d3e7ca7bf48d50; required/Artist/compatibility host Green |
| P8 Hub final audit/symlink/Consumer correction | Hub #98 | 17e60ce820164efc2cea59c415d29717ac6f103c; required/Artist/compatibility host Green |
| P8 Agent final layout/pin/audit | This final PR | Local gate and cross-repo proof below; required Canonical must be Green before squash merge |

P5 canonical: original28 validators and10 suites retained,2 suites added;624 cases,1 Windows skip. Clean rebuilt sdist/wheel installed outside checkout into a fresh venv;228 hashes, help/doctor/policy/catalog/context/fingerprint/schema loads PASS. Required CI initially found missing setuptools on Python3.12; explicit build dependencies fixed it, then CI passed. Local network-dependent builds failed until cached dependency wheels and no-isolation build were used; only the newly built offline artifact proof is reported PASS.

P8 adds strict layout ownership independently of domain authority; unknown/old roots, prohibited directory, external/dangling authored symlinks, missing canonical paths and ambiguous authority are rejected. Eight tests include reproduced symlink regression RED→GREEN. The final Source Lock pins Hub 17e60ce820164efc2cea59c415d29717ac6f103c with Hub/Tools, Hub/Registry, Hub/SubAgents and cli/artist. Actual Development/Pinned use isolated committed Git archives and return identical read-only no_op, no catalog write; snapshot SHA-256 ac62220716ac087327228dfc58e1d10db7dc7e438e1407e865d2d752242499a8.

Immutable P0 inventory remains historical; exact551 Agent path map and Hub migration/hash indexes preserve provenance. All23 Agent UPM files remain byte-identical. Hub product code/meta/package identity and77 frozen source records remain protected; owning documentation paths changed. Original checkout's unrelated fixture newline difference remains untouched.

No actual Unity Editor/license/rendering/Player/device/Windows Named Pipe execution passed. These gates remain BLOCKED_NOT_RUN. Hub run38066203244 provides three blocked canonical/minimal artifacts, IDs11674463178/11675213275/11674293315, expiry2026-10-24. Pipeline and dynamic Canary implementation are ready; direct official metadata reads from Cloud were proxy403. Provision/replay commands and exact version evidence are in Hub docs/migration/unity-ci-foundation.md. This is Cloud implementation completion, not full E2E completion.

Final P8 host proof:29 validators and original10+2 suites,633 cases (one Windows skip), graph/YAML gates PASS. After final Hub pin17e60ce, Development/Pinned imports are both no_op. Newly built sdist, pip wheel and fresh installed-wheel outside-checkout proof PASS;228 resource hashes; wheel SHA-256 8b369c6f60ec8a681b15e52a42855dfd006c9163857b64560fda2e1ffb7659b9. UPM npm pack23 entries PASS using workspace cache. Direct canonical/minimal/Built-in/URP/HDRP attempts each exited2 with BLOCKED_NOT_RUN evidence because a prelicensed runner is unavailable. Required CI must independently pass before final squash merge.

Final reference audit preserves the Context Explorer schema $id as public identity and restores the pre-migration Unity Tools menu label; neither is an authored filesystem dependency. No current path authority is assigned to historical/negative-test/external-package strings. Hub's old-path change-detection prefixes only detect removed historical paths and do not load them.

Final independent review found a Python namespace replacement had also changed five public Unity C# namespaces. Restored UnityAgent.Runtime.Harnesses.Unity.Editor and confirmed all five complete C# files byte-identical to the P0 Git baseline. Public-type namespace regression failed before and passed after the correction; final canonical now633 cases. This is static identity preservation, not an observed Unity compile PASS.

# SubAgent in-repository migration — Stage 1

UnityAgent/subagent/ is the preferred canonical destination for the four existing SubAgent sources. No user-facing Mode is introduced.

Imported in this stage:
- Registry, Manifest v5, Schema, instructions, contracts, admission record, snapshot exporter and selected tests for Artist, Graphics, Performance and WorldCreator
- Original identity, capability names, execution kind, backend separation and activation requirements preserved
- Automatic install remains disabled; Graphics and Performance remain read-only and WorldCreator remains planning-only

The import source is the fixed UnitySubAgentHub commit c5a593dfcaeea0f902999e91a97b620214db063f.

## Transitional dual-source boundary (not final migration)

The current UnityAgent runtime Consumer Catalog, Artist CLI/UPM and P9 fixtures still use the legacy Hub-pinned integration. Do not remove Source Lock or Hub verification provisioning until Artist implementation, Unity fixtures, toolchain discovery and package builds have been migrated and tested.

Next gates:
1. Bring Artist backend/package and CI fixtures into UnityAgent without rewriting GUIDs or serialized identities.
2. Replace dual Hub/Consumer definitions with a single validated in-repo source and explicit consumer-specific profiles.
3. Extend existing fast_path and ParentGraph to Fast/Standard/Orchestrated Adaptive Execution, with explicit user selection, resource leases and evidence-backed acceptance.
4. Replace Editor's Hub fetcher with in-package/local source test orchestration; remove redundant Hub source pins only after packaging and actual Editor E2E tests.

CI host contract success does not imply real Unity Editor/P9 PASS. Historical evidence remains read-only. Never auto-upgrade read-only SubAgents to code-mutating executors.

# UnityAgent Migration History

`docs/migration/`は、過去のArchitecture移行、Cutover、Baseline更新、Compatibility削除を監査するHistorical Recordです。ここに残る旧Path、旧Contract、旧Phase名は当時の状態を示し、現在の仕様ではありません。

## Current authority

現在のUnityAgent behaviorは次を優先してください。

1. `AGENTS.md`
2. `Policy/`、`Orchestration/`、`Context/`、`Runtime/`、`Persistence/`、`Operations/`、`Eval/`のCanonical Source
3. [Architecture](../architecture/architecture.md)
4. [Production Tool Runtime](../architecture/production-tool-runtime.md)
5. 関連する`Specs/`

このDirectoryはRouting、Context Materialization、Runtime Execution、Policy判断にCurrent Stateとして使いません。UnitySubAgentHubは別RepositoryにあるSubAgent metadata contractの所有者です。現在のHub SnapshotはUnityAgent Runtimeへ自動取込されないため、Migration Recordをその代替として使わないでください。

## 残す理由

- Authorityをどこへ移したか、何を削除したかを追跡する
- Historical Replay / Baselineの出所を監査する
- Current Contractに至った移行判断を読みやすく保つ

主な記録は`canonical-contracts.md`、`policy-context.md`、`runtime-harness.md`、`orchestration.md`、`persistence.md`、`eval-consolidation.md`、`operations.md`、`cutover.md`、`production-rebaseline.md`、`baseline-comparator.md`、`production-tool-runtime-cutover.md`です。

## Historical Pathと名前

過去のBranch、Run ID、Artifact、Baseline、旧Path、旧Contract名は、Historical Evidenceとの対応を保つため原文のまま残せます。`.ai/**`、`Context/Selection/mcp-selection.yaml`、`compatibility://...`などを現在のAuthorityとして復活させません。

ファイル名はPhase番号より責務を表す名前にします。Migration文書とCurrent Canonical Sourceが競合した場合は、Current Canonical Sourceを優先します。

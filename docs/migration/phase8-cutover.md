# Phase 8 — Cutover / Human Gate

## Goal

UnityAgentをcanonical single-repo authorityへ切り替え、旧 `.ai` authority、Context/Eval/Persistence compatibility、old Eval shims、old LoopIntegration control plane、Unity-Graph-Engineeringのproduction dependencyを除去する。

## Cutover order

1. Canonical replacementを先に作る。
2. Active referencesをcanonical pathへ切り替える。
3. Canonical Policy/Context/Runtime/Orchestration/Persistence/Eval/Operations regressionを通す。
4. Legacy/compatibility treeを削除する。
5. `Eval/Behavior/validate_phase8_cutover.py` でactive fallback/shim/dependencyがゼロであることを確認する。
6. ARCH/NAMING/MUTATION/EVIDENCE historical replayを実行する。
7. UnityAgent単体のcontrolled Production Smokeを実行する。
8. Human Gateでcutover結果を確認してからmainへmergeする。

## Canonical ownership after cutover

- Policy: `Policy/`
- Context: `Context/`
- Orchestration / Task Contracts: `Orchestration/`
- Runtime / Harness: `Runtime/`
- Persistence: `Persistence/`
- Operations: `Operations/`
- Eval / Historical replay: `Eval/`

## Historical provenance

過去のmigration事実、Golden/Eval fixture、historical execution envelopeは監査事実として `docs/migration/`、`Eval/Datasets/`、`Eval/Replay/` に残してよい。これらはproduction authorityとしてresolveしない。

## Human Gate

以下がすべて満たされるまでmergeしない。

- canonical CIが全Green
- `.ai` / compatibility / old shimsがactive treeから消えている
- active Unity-Graph-Engineering execution dependencyがゼロ
- ARCH/NAMING/MUTATION/EVIDENCE replayがlossless
- one-repo controlled Production Smokeが観測済み、または実行不能理由を `unavailable` として明示
- User Policyにlossがない

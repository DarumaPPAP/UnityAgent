# Adaptive Execution / SubAgent統合実行方針

UnityAgentが唯一のControl Plane。SubAgentは \`subagent/\` の独立した
Manifest / Instructions / Contract / Testを正本とし、「Mode」のUXは導入しない。

## Coordinatorの決定的な3経路

1. **Fast** — 単一の低リスク・既知Scope・既知Project・Review不要Task。
   UnityAgentが直接処理し、SubAgent・ParentGraph・Worktreeの追加コストは発生させない。
2. **Standard** — 一つのSubAgentが担当するTask、または追加設計・検証が要るTask。
   SubAgentは明示選出/自動選出を両立。Contextを必要範囲に制限する。
3. **Orchestrated** — 複数Task、複数SubAgent、競合するリソース。
   Task DAG / Project Resource claimによって直列・並列を計画し、独立する変更のみ
   別Worktreeに分割する。最終の統合E2Eは同一Revisionで判定する。

\`select_execution_path\` は *plan-only* な選択ロジック、
\`plan_task_batches\` は *plan-only* なDAG/リソース競合検出であり、
どちらも権限を発行せず実際のUnity Editorを起動しない。
現行\`orchestrator.fast_path\`を置換せず、ルーティング→Runtime handoff間の
段階的導入に使う。Runtime側のLease取得・実Projectへの反映・新E2E Capabilityは
別Gateの実装が必要で、現段階でE2E完全実装とは主張しない。

## 許可とEvidence

小さいTaskでもPolicy / Approval / Project binding / Mutation scope / Evidence必須。
予算は既存\`context/budget/context-budget.yaml\`の
\`tight / standard / wide\`を流用。推定値を実測モデルTokenと誤称しない。
同じUnity ProjectのEditorを別プロセスで同時に開かない。
RuntimeによるResource Leaseが観測・獲得される前に
planの\`parallel\`判定を実行許可へ昇格させてはならない。
Unknownや競合はBLOCKED / 待機にする。

## 追跡中の段階

- SubAgent定義の同居: \`subagent/\` 移植済み
- Artist Package/CLI: 同居済み
- Adaptive選択/DAGリソース計画: 本変更
- Unity Editor P9検証経路: UnityAgent UPMへ同居P9/Artist Fixtureを同梱済み。
  Setupは外部Hub Git取得を使わず、同梱Manifestを照合して別Editorで実行。
- SubAgent Catalog Import Gate: UnityAgent内の`subagent/` Manifestから作った
  SnapshotがConsumer Catalogとread-only/no-opで一致することをCIで検査。
  外部Hub checkoutをProduction PR検証時に取得しない。
- RuntimeへのLease/Queue接続、SubAgentごとの変更権限付きE2E能力、
  互換のため残るLegacy Hub Source Lock/Import CLI撤去: 未完了。

## Control Plane接続（2026-10-14）

Entry v2の任意`requested_subagent`は既存Route担当と照合し、activation gateを維持する。
Adaptive選択は実際のControl Plane実行に接続し、Orchestration decisionへ保存する。
Project inspectionはFastで追加Agent/Worktreeを作らず、単一専門TaskはStandardとなる。
現行Entryは1タスクだけを受け付けるため、DAG plannerのparallel提案を実行許可にしない。
同一Projectへの実行はRuntimeのOS file lockで排他し、Evidence保存まで保持する。
別Persistence rootも同じHost/userのlease領域を使い、TTLだけで所有権を奪取しない。
競合は`blocked/resource_busy`。Queue/Heartbeat/Device Lockはまだ有効化しない。
Releaseは同居sourceを使い、Python配布にはSubAgent定義も同梱する。

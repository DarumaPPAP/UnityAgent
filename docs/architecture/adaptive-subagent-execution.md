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

## Runtime Project排他（実装段階）

`runtime/execution_control/resource_lease.py`はEditorを利用するCapabilityと
Mutation操作について、ユーザー領域のProject実体Path Hashに基づく
排他Leaseを発行する。最後のGuardの後、Provider実行前に確保する。
拒否時は`resource_conflict`でBLOCKED。別ProviderへFallbackして抜け道を
作らない。Heartbeatは監査情報であり期限切れで自動奪取しない。
壊れたLeaseや残留LeaseはRuntimeが自動削除せず、Editor停止を観測した
明示的なRecovery手順が必要。

これは**UnityAgent Runtime経由の処理同士**の排他であり、Editorの
手動操作やUnity自身のProject Lockとの統合、Workbench/Worktree統合、
Task SchedulerのLease待ち行列、Console実機排他、E2E Mutation Grantまで
完成したという意味ではない。Fast Pathのread-only source readは
Leaseを取得せず、Tokenを増やすOrchestrationを追加しない。

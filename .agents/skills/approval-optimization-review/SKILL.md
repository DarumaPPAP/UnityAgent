---
name: approval-optimization-review
description: Use when reviewing repeated or slow UnityAgent human-approval stages from durable Evidence and Eval results and preparing a read-only optimization proposal without altering approval authority, scope or safety gates.
allowed-tools:
  - Read
metadata:
  version: "1.0.0"
  kind: evidence-gate
  entrypoint: false
  user_policy: src/unityagent/policy/user/user-policy.yaml
---

# Approval Optimization Review

このSkillは**読み取り専用**。既存の承認待ちやStage間停止のコストを、実測Evidenceから評価する。承認・Policy・Scope・Runtime・永続Stateを**変更しない**。

## When to use

- 承認待ちの回数、遅延、再実行コストが実測された後
- 同種の承認をまとめる案や通知タイミングの変更を検討するとき
- 既存Stage Acceptanceに安全性回帰がないか監査するとき

まだWorkflowが未実行、またはEvidenceがない場合、提案の効果は `unmeasured` とし「改善済み」と書かない。

## Inputs and authority

- 読むもの: `src/unityagent/persistence/approval/approval_store.py`、既存PersistenceとEvidence Storeの参照、`eval/`の測定結果、実行されたPlan Digest・固定Source SHA・対象Project Revision
- 必須比較: 同一条件のBaseline / Candidate、承認回数・手待ち時間・Latency・Token / Cost、拒否率、失効・取消・中断・Resumeの観測
- 権限: UnityAgent Control PlaneのみがPolicy / Approval / Orchestration / Runtime / Persistence / Evalの正本を管理する。GitHubのイベントは認証済み承認証跡であり、GitHub Actionsの入力だけでApproval Decisionを作らない
- 評価対象の検証レベル (G0 / G1 / G2 / G3) はEvidence metadataにだけ記録し、Skill名やフォルダ名にしない

## Review workflow

1. Source Revision、Logical Run、Plan Digest、対象Project Revision、Evidence参照を確認する。欠落していれば `BLOCKED_NOT_RUN` / `not_observed` を維持する。
2. Approval DecisionのScope、承認者認証、期限、失効Epoch、変更範囲、保存承認、Rollback承認、Visual承認を区別する。観測されない承認を既承認扱いしない。
3. 同条件のBaselineとCandidateの承認待ち・CI停止回数・再実行回数・時間・Tokenを比較する。推定は推定と明記する。
4. もっとも安価な代替案（通知の改善、Stateを保存してRunnerを終了、承認待ちをまとめる案）を比較する。短いTaskに新しいSubAgentやWorkflowを強制しない。
5. 承認の自動集約、Scope緩和、期限延長を直接実行しない。B案のBundle承認はHuman Reviewと別PR / 回帰検証を必要とする将来候補としてのみ扱う。
6. 既存`eval/change_proposals/change_proposal.py`の`build_change_proposal`契約で、Eval根拠と最小変更案を提案する。記録の作成・保存・PR作成自体は本Skillの実行権限外。

## ChangeProposal contract

`proposal_id`、`source_eval_refs`、`target_authority`、`proposed_change`、`rationale`、`evidence_refs`を明示する。既存関数の結果は必ず `status: proposed`、`applies_change: false`、`requires_human_review: true` を維持する。新しい独立Proposal Storeを追加しない。

承認最適化は、実際のApproval Decisionを作る操作ではない。Reviewで承認対象のPlanやArtifactを変更しない。未観測のEditor / Visual / Rollback / Player / 実機GateをPASSへ昇格しない。

## Output contract

- 対象Run / Source SHA / 固定条件 / 評価対象Level
- Evidenceと不明点（Fact / Hypothesis / 未観測を分離）
- Baseline対CandidateのLatency、承認回数、Token・費用（測定値と欠損）
- リスク: Scope変更、失効・取消、Double-Run、Editor Lease、Rollback、Visual承認
- 推奨案、必要なHuman Review、別PR・Regression・Baseline比較
- Proposed ChangeProposal payloadのみ（実適用なし）

## Scope

- ファイルを変更しない。Approval Decisionを発行・失効・再登録しない。
- Githubイベントや自己申告の `approved=true` を承認証跡として信頼しない。
- Mutation Scopeの拡大、承認ステップの省略、Human Visual / Rollback署名の一括代替を行わない。
- 実装・Merge・Release・自動改善の実行を行わない。

## Checklist

- [ ] 現行Evidence / Baselineの有無と鮮度を確認した
- [ ] Approvalの本人性・Plan Digest・Source Revision・Scope・期限・失効を別々に確認した
- [ ] 不確定な副作用を再実行許可へ変換していない
- [ ] 数値が未測定なら `unmeasured` とした
- [ ] VisualとRollbackのGateを個別に維持した
- [ ] Proposalが人間のレビュー必須かつ非適用である

## Common mistakes

- Workflowのステータス成功をControl Plane承認と取り違える。
- 実測なしの「5回の承認を1回にした」を改善事実とする。
- Source SHA / Artifact Hash / Project Revisionの変更後も古い承認を再利用する。
- 停止時の `RUNNING` を安全な `READY` に戻して二重Importする。
- 提案生成とPolicy更新・自律改善を混同する。

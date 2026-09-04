# UnityAgent 品質レビュー（2026-09-04）

> Review snapshot / non-authoritative。これは `main@e8988ca7b8c656b6c3b6bc7ae592a9925d674d51` の状態を判断するための資料であり、Policy、Architecture、Runtimeの正本ではありません。

## 結論

総合判定は **Rework / Evidence Required** です。

Policyから各責務への境界、Provider解決の設計、Evidenceを不変記録として扱う意図、静的な契約テストは良好です。一方で、Mutationを安全に隔離する境界、ApprovalとExact Diffの照合、必須Evidenceの完了Gate、OrchestrationからRuntime・Persistenceまでの本番結線が受入条件を満たしていません。Unity Editor、MyUnityMCP、Player、実機性能の証拠も現時点では未取得です。

| 領域 | 判定 | 判断理由 |
| --- | --- | --- |
| Authority境界 | Strong | `Policy → Orchestration → Context → Runtime → Persistence → Operations/Eval` の責務が文書と実装に明示されている |
| 静的契約・単体検証 | Strong | クリーンなHEADで `Tools/validate_all.py` の320テストが成功 |
| 本番実行結線 | Rework | Runtime Handoff、ToolBroker、Evidence Persistenceを通る単一Composition Rootが確認できない |
| Mutation安全性 | Rework | Runnerが変更後にScope違反を検出し、承認とExact Diffも独立に検証されない |
| CI・検証の信頼性 | Partial | 収集外テスト、0件実行Workflow、ignoredファイル依存、未接続Validatorが残る |
| 実環境・性能Evidence | Evidence Required | Unity/Editor/Player/実機/Profilerの再現可能な実行証拠がない |

## 判断の要点

1. **先に安全境界を閉じる**：read-only実行とMutation実行を分離し、承認、Scope、Exact Diff、Evidenceを実行完了前に検証する。
2. **Canonical Flowを1本化する**：OrchestrationのHandoffからRuntime Guard、ToolBroker、Resolver、Dispatcher、Evidence Normalizer、Persistenceまでを一つの信頼できるComposition Rootで接続する。
3. **検証を信頼できる入力にする**：テスト収集、0件実行防止、tracked-only判定、Graph Observatory、古い契約・文書の整理を行う。
4. **実環境で証明する**：Windows、Unity Editor/CLI、MyUnityMCP、Player、対象機器のケースを固定し、成果物のダイジェストと保存先を持つ。

## 資料の読み方

- [現状構成](current-state.md)：責務、規模、宣言と実装の差分。
- [実行フロー](execution-flows.md)：Canonical Flow、現在のSmoke経路、目標となる安全Gate。
- [課題一覧](findings.md)：`UA-Q-001` 形式の根拠付きFinding。
- [改善ロードマップ](improvement-roadmap.md)：依存関係を含むStage 0–4の修正順序。
- [Evidence台帳](evidence.md)：コマンド、GitHub履歴、検証限界、未観測領域。

## スコープと前提

- 対象はローカルのCanonical Sourceと公開GitHub履歴（PR #92、PR #91、Issue #32）です。
- 今回は資料作成のみで、Production code、設定、Policy、GitHub Issue/PRは変更していません。
- 未実行のUnity Editor、MyUnityMCP、Player、実機、性能計測を推測で補いません。
- 改善案は受入条件を明確にするためのレビュー提案であり、自動的な実装承認ではありません。

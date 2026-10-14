# SubAgent Execution Cutover Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. このセッションで直接実装する。

**Goal:** 統合済みSubAgentの配布と既存Control Plane実行経路を接続する。
**Architecture:** 既存のSource、Resolver、Adaptive selector、Evidenceを利用する。権限拡張は実装・検証されるまで有効化しない。
**Tech Stack:** Python 3.10+、unittest、YAML、GitHub Actions、OS file locks。
**Spec:** docs/superpowers/specs/2026-10-14-subagent-execution-cutover-design.md

## Global Constraints
- UnityAgentが唯一のControl Plane。配置は`subagent/`。Mode UIなし。
- GUID/ID/optional install/Approval/Context/Evidence契約維持。
- 実Editor・実機成功をHost testで代用しない。

## Review Focus
- sdistからwheelへ再BuildしてもInstructions/Contractsが欠落しない。
- 指定SubAgent不一致・未導入は別Agentに黙ってfallbackしない。
- symlink alias・別プロセス・別Persistence rootでも同じProjectは競合する。
- 処理失敗後ロックが残らず、稼働中の所有者を期限で奪取しない。
- Releaseの全SubAgent成果物は同一checkoutに由来する。

### Task 1: 配布源切替
- [x] 実resource copyとRelease workflowの回帰テストを先に追加し失敗を確認。
- [x] setup.py/MANIFEST.inに正本SubAgent resourcesを追加。
- [x] ReleaseのHub checkoutを除去し同居CLI/UPM/exporterを使用、provenanceにUnityAgent SHAを記録。
- [x] wheelとsdistのBuild、抽出、正本hash照合。

### Task 2: 明示選出とAdaptive接続
- [x] Entry v2の明示指定一致/不一致・実decision永続化のControl Planeテストを追加。
- [x] requested_subagentをSchemaへ追加しRoute ownershipと照合。
- [x] select_execution_pathをControl Planeへ接続。decisionに保存。
- [x] 既存activation/context gateとRuntime handoffの回帰を実行。

### Task 3: Project排他
- [x] 別プロセス/alias/例外/別Projectの取得テストを追加し失敗を確認。
- [x] Runtimeに同じHost/OSユーザーで共有するProject OS leaseを実装。Control Plane.executeを包む。
- [x] 同Project競合はBLOCKED、同Project処理終了まで解放しない。
- [x] validate_all、全差分review、PR作成。未実装のE2E権限・Queue/Device/Graph実行は明記。

## 検証記録と実行上の判断

- `python tools/validate_all.py`: PASS。追加テストはRED→GREENを確認。
- `python -m build`: wheel/sdistを生成、正本SubAgent関連30件のbytes/SHA-256一致を確認。
- `tools/verify_installed_wheel.py`: checkout外のvenvでinstall/Context/doctor検証PASS。
- Project lease: 7ケース。別プロセス、alias、環境変数変更、例外解放を確認。
- 独立review: ロックnamespaceの環境依存を修正。Windows identity期待値を正規化。
- FastはParentGraph読込を省略する。Resume互換の最小WorkflowStateとEvidence保存は維持する。
- OS leaseは同じHost/OSユーザー間の協調制御。別ユーザー・非協調Editorの排他は保証しない。
- ReleaseはUnityAgentの既存正本Validator/CLI regression/P9 fixture Gateを使用する。
  移植した旧Hubのhistorical source verifierは旧Path/Tag依存があるためRelease入口にしない。
- Windows OS leaseは専用CIへ追加。ローカルに.NET/Unity Editorはなく、CLI Compile/実Editor/実機はここで検証していない。
- 元の設計の残り: 複数Task DAG実行、Queue/Device Lock、専門SubAgentの変更権限付きE2Eと統合Acceptance、旧Hub Archive。

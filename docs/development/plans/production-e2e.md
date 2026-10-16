# Production E2E implementation plan

Spec: `docs/decisions/production-e2e/approved-goal.md`（ユーザー承認済み）。既存構造・Python標準ライブラリ・既存PyYAML/jsonschemaを利用。Unity packageの導入/更新、外部生成課金、merge/release/tagは行わない。

実行方法は本チャットでの実装。先にPhase 0、次にPhase 1〜4。各変更はテスト失敗を観測してから実装し、依存単位でcommit/PRに分ける。

1. **Phase 0**: Decision原文・Baseline・Gap・Architecture・回帰Matrixを正本化。新旧Repository Layoutの重複を持ち込まない。
2. **Phase 1**: `orchestration/graph/resource_planning.py`を再利用し、Control PlaneのTask DAG入口を追加。既存`execute`のみが実行権限を所有。Task identity、固定Gate、Definition/Project Revision、Evidence、Budget、handoff履歴を既存StateStoreのsnapshotへ保存。未検証依存は実行しない。既存CheckpointのState復元と外部副作用照合を分離。StagingはAsset/metaのHash比較後だけ限定Rollbackし、他者変更で停止。
3. **Phase 2**: `performance_subagent`をQAへ移行し、旧IDの明示aliasを維持。性能分析Schema/Capabilityは維持。WorldCreator用の制限付きBlender MCP adapter、永続Job identity、Session排他、Timeout時の照合を追加。既存Setup Doctorでoptional Backendを観測し、未検出でも他のCapabilityを停止しない。
4. **Phase 3**: `ci`へUnity 6.3 URP G1 fixtureとWindows Runner手順・E2E検証を追加。AssetDatabase/PrefabUtility/Scene APIを使用。FBX検査・再Import・GUID/参照維持・Rollback競合を検証。実行できないGateを`BLOCKED_NOT_RUN`として出力。
5. **Phase 4**: Runtimeにoptional Loop Hot Reload adapterを追加。Project/Source Revisionを確認し部分/Skipped/Failedを拒否。通常Compileを別Gateとして残す。比較は同一Taskの観測サンプルのみ集計し、token未取得は`unmeasured`。G2/G3は別Evidenceとする。

## Review focus

- Task失敗後の子Task、重複id、Cycle、Revision不一致、再開中の未確定副作用は停止する。
- QAが返すGateの欠落・別Revision・他TaskのEvidenceでVerifiedにしない。
- Timeoutが送信済み外部Jobを重複生成しない。
- Stagingのsymlink/path traversal、他者によるAsset/meta編集で自動復旧しない。
- Hot Reloadの部分成功と通常Compile/Player/Visualの未観測を成功にしない。

## Validation

各Taskのfocused unittest → 既存関連suite → `PYTHONPATH=src python tools/validate_all.py`。CIとUnity実E2Eは別々に報告。PRはmainをbaseとし、積み重ねた変更は依存Commitを明記する。

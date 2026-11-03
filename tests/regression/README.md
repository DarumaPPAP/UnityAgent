# Phase 1 — 限定Python Regression

目的は、旧Regressionを件数ベースで復元することではなく、現行Productionの危険な失敗条件を既存の `unittest` と実FSで再び検出すること。旧テストの復元・新しいFramework・別Runnerは不要。

## 実行

```bash
python -m pip install -e .
python -m unittest discover -s tests/regression -p "test_*.py" -q -b
python tools/validate_all.py --profile static
```

PRの必須CIは限定RegressionとStatic/Packagingを**別ステップ**で実行する。単一テストを実行する場合は `python -m unittest discover -s tests/regression -p "test_approval_boundary.py" -q -b` のように指定する。

## 採用ケースと責務

| Module | Invariant / Failure prevented | 通す実境界 | 未検証 |
| --- | --- | --- | --- |
| `test_approval_boundary.py` | 取消epochの巻戻し、Plan差替、失敗検証後の誤消費、単回承認の再利用、C#承認の取消・Scope不一致・期限切れ・Revision変更によるDispatch前停止 | `ApprovalDecisionStore`、`csharp_fix.before_capability` の実判定、実FS・OS Lock。Storeの外部検証CallbackのみStub/Spy | Human承認発行の真正性、汎用/Artist認可、実ToolBroker DispatchからEditorまでのE2E |
| `test_mutation_boundary.py` | 許可範囲のPrefix衝突、禁止Scope侵入、非変更Taskの変更、Traversal、C# preimageへのコメント混入、Assets外・Alias対象への適用 | 実 `evaluate_mutation_scope`、`source_target`、`validate_csharp_patch`、`patch_revisions` とテスト所有Project FS | 実Tool適用後のSnapshot比較、Provider境界、Editor上のMutation |
| `test_persistence_integrity.py` | Immutable Recordの上書き、破損JSON、Root脱出、別Run State、Evidence Record・Event Chain改竄、別Run Evidenceの誤利用、未確認Observation再利用 | `StateStore`、`EvidenceStore`、`atomic_store` の実保存・再読み込み | Crash途中復旧、Checkpoint/Resume、同時書込/Windows Lock、実Unity E2E |

- 各ケースの境界入力・期待値はテスト内に残す。共通化はFS資源の所有管理と最小限の正当EvidenceRecord生成に限定。
- 意図した失敗を検出するため、正しく受理すべきケースと拒否ケースを併置する。単なるMock戻り値のAssertionでは成功としない。
- TemporaryDirectoryとテスト所有のAssetだけを使用する。Symlink / Hardlink作成がOS権限上できなければケースは`skip`し、PASSと報告しない。
- Python CIのPASSはUnity Compile / EditMode / PlayMode / Player / 実機 / VisualのEvidenceではない。

## 残存リスクと次段階

これは**Phase 1の第一スライス**。保護しているのはStoreとScopeの局所境界であり、Approval → Tool Dispatch → Applied Mutation → Evidence → Resume の実行経路全体ではない。旧Baseline `77483d6ecc656b8842954cd509de5d9ce7224c2f` のRegression同等性は証明しない。

次段階は以下の順に既存Moduleを拡張する。

1. Approval発行からToolBroker実Dispatchまでの統合回帰（偽造、別Run/Project、取消、適用後監査）。C#のDispatch直前Verifierだけは本スライスで部分観測済み。
2. File Provider等の実変更境界で拒否時の無変更・許可時の変更・監査の保存を確認する回帰。
3. PersistenceのCheckpoint、Recovery、Resume、Evidence改竄を現行Contractで再検証する回帰。
4. Windows OS LockとUnity `tests/UnityAgentTest` の手動実Editor Evidenceを別Gateとして記録する。

検証失敗は対象契約・環境・Source SHA・期待Failの理由を記録して修正する。未観測をPASSとしない。ReleaseのFail-Closedは本スライスでは解除しない。

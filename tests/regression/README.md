# P0 — Python安全性Regression

旧Regressionの件数復元ではなく、現行Productionの保護Invariantと故障検出力を検証する。既存Python unittest、実FS、実署名HTTP、実子Processを使用し、新規Frameworkや依存を導入しない。

## 実行

```bash
python -m pip install -e . build "setuptools>=68" wheel
python -m unittest discover -s tests/regression -p "test_*.py" -q -b
python -m unittest discover -s .github/ProductionSmoke -p "test_*.py" -q -b
python tools/validate_all.py --profile static
python -m build
python tools/verify_installed_wheel.py --wheel <今回生成したwheelのパス>
```

Windowsでは書込み可能な専用一時領域をTEMP/TMPへ指定する。CIは空Suite・SkipをFail Closedとし、RegressionとStatic/Packagingを別Stepで実行する。実行ログは `p0-regression-<CI SHA>` Artifactへ保存する。個別Moduleはdiscoverの `-p` で指定できる。

## 保護Invariantと対応表

| 領域 / Module | 実行する実経路・観測 | 保護する失敗 | 代替依存・未達 |
| --- | --- | --- | --- |
| Approval / `test_approval_boundary.py` | 実register/approve、Resolver、ArtistAuthorityのloopback HTTP/HMACと応答署名、永続消費、Control Plane `execute_artist` の承認判定からDispatch境界。既存C# Gateも維持 | 不正署名、期限到達、別Project、セッション開始後取消、二重消費、Plan/Revision/Scope差替。拒否時は未消費・元Source無変更 | Editor Plan観測はテスト所有データ。Control PlaneケースのContext準備・Editor発見・Dispatch先は代替。実Editor ApplyとHuman承認の真正性はBLOCKED_NOT_RUN |
| Mutation / `test_mutation_boundary.py` | 実FileProvider適用、全Projectの独立FS差分、Runtime execute → 実子Process → 実FileProvider → 適用後Snapshot/Scope → mutation-evidence.yaml | Traversal、Scope Prefix、禁止優先、別Project、古いpreimage、承認不足、正常終了後の余分なScope外変更 | Agent CLIの判断をテスト所有の決定的Processで代替。実Agent推論品質・Editor MutationはBLOCKED_NOT_RUN |
| Persistence / `test_persistence_integrity.py` | 実State/Evidence → Checkpoint → evaluate_resume → restore、実子Processのatomic replace直前os._exit、実Control Plane Task DAGの中断後Resume拒否 | 破損JSON/Checkpoint Hash、別Run Snapshot、Evidence改竄、定義非互換、Action発行後Context変更、実行中外部副作用の不確定性、Currentの部分上書き | DAG子実行の中断はSystemExitで注入。電源断・Disk障害・全restore書込み間の強制終了の原子性は未保証。Unity Asset復元は対象外 |

- 正常系を併置し、無条件拒否・何もしない実装を検出する。
- Evidenceの期待値は正本Schemaにも照合し、Event自身のHashと前Eventへの連結を独立検証する。
- **CheckpointのEvidence refsは、Task DAGが明示した子Run unionを許容する既存契約。** 各Record自身のRun/Event Chain整合性をverify_recordで確認する。任意の別Run Evidenceを親子関係で拒否する仕組みは現行Schemaにない。Checkpoint/SnapshotのRun identityと混同しない。
- restoreはCurrent Stateだけを戻す。後から追加されたEvidenceを保持し、Checkpoint後に追加したLoopを残さない。
- RuntimeのScope違反検出は失敗状態とEvidenceを返す。既に行われた悪意ある子Processの変更を自動Rollbackする契約ではない。拒否されたFileProvider要求については元ファイルの無変更を確認する。
- TemporaryDirectoryだけでFixtureを所有し、ユーザーAssetや既存Projectを再利用しない。Symlink/Hardlinkを作成できなければSkipし、PASSへ換算しない。

## 故障注入の再現

テストを先に実行して正常を確認し、以下の置換を `unittest.mock.patch` のContext内で1種類ずつ適用して対象1件を実行する。製品ファイルは書き換えない。置換解除後に全Suiteを実行する。

| 故障対象（完全修飾名） | 一時置換 | 検出するテスト |
| --- | --- | --- |
| `unityagent.control_plane.artist_authority.hmac.compare_digest` | `lambda *args: True` | `SignedAuthorityTests.test_invalid_signature_cannot_consume_or_block_later_valid_request` |
| `unityagent.runtime.tooling.providers.file.file_provider.evaluate_mutation_scope` | `lambda **kw: {"status": "passed"}` | `FileMutationTests.test_prohibition_overrides_allowed_scope_before_write` |
| `unityagent.persistence.checkpoint.checkpoint_store.EvidenceStore.verify_record` | `lambda *args, **kw: None` | `CheckpointRecoveryTests.test_tampered_evidence_prevents_checkpoint_creation` |
| `unityagent.persistence.checkpoint.checkpoint_store.CheckpointStore.restore` | `lambda *args: None` | `CheckpointRecoveryTests.test_resume_and_restore_exact_state_preserves_later_evidence` |
| `unityagent.runtime.runner.codex.codex_runner.evaluate_mutation_scope` | `lambda **kw: {"status": "passed", "scope_status": "within_scope"}` | `FileMutationTests.test_runtime_fails_closed_on_actual_extra_change_after_provider` |

実行例（対象Moduleは `sys.path.insert(0, "tests/regression")` で読込む）：

```python
with patch(target, replacement):
    suite = unittest.defaultTestLoader.loadTestsFromName(test_name)
    result = unittest.TextTestRunner(buffer=True).run(suite)
assert result.testsRun == 1 and len(result.failures) == 1 and not result.errors and not result.skipped
```

意図したAssertion FAILだけを検出成功とし、Import/Fixture/環境Errorは数えない。

## 採用・未達の扱い

追加は既存3 Moduleに統合し、資源管理と同一責務の準備だけを共通化する。Invariantが現行契約から撤去・変更された場合だけ通常PRで変更・廃止する。実行コスト・対象SHA・実際の故障結果・Actions URLはPRに記録する。旧Baseline `77483d6ecc656b8842954cd509de5d9ce7224c2f` との同等性は主張しない。

P1の実Unity Compile / EditMode / PlayMode / Player / Device / Visual、Windows OS Lockの専用競合試験、実Agent品質EvalはBLOCKED_NOT_RUN。P0 Python成功へ混ぜず、ReleaseのFail Closedを解除しない。

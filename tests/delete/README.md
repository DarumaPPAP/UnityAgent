# 凍結済みテスト（置換期間専用）

このディレクトリは、旧テストを新しい小規模スイートに安全に置換する期間の一時的な置き場です。**恒久アーカイブでも、新たなテスト正本でもありません**。旧テストが存在するという理由だけでProduction機能を維持しません。

## 運用

- テストは機能上の責務と検出するFailureによって分類する。関連する小さなケースは一つのTest Moduleにまとめるが、異なる責務や実Unity E2Eは巨大な一ファイルへ統合しない。
- 旧ファイルを移す際は内容を変更せず、元のGit BlobとBaseline Revisionを記録する。凍結中のTestは通常のCanonical Suiteに自動登録しない。新Testが未完成な領域の旧Testは通常の実行場所から移さない。
- 新しい最小Testは現行仕様・安全性契約・過去の不具合から設計し、成功Evidenceだけでなく重要な拒否・失敗系も守る。
- 置換した領域は**元のBaselineで旧TestがPASSしたこと**と、**新スイートが同じ重要なFailureを検出できること**を確認してから旧Testを削除する。単なるテスト件数削減、モックだけのPASS、未観測E2Eは根拠にしない。
- 新たなテストは最初にTask専用の一時Worktree／`TemporaryDirectory`等で試す。Task終了時に不要な一時テストを清掃。恒久採用が必要なら、既存のChangeProposal（Eval改善時）または通常PRに「守るInvariant・既存Testとの差分・失敗リスク・維持コスト」を示してレビューする。新しいApproval Authorityは設けない。
- CIの既存必須Gateは新しい正本の整合が確認できるまで継続する。対象外の旧Testを一括移動してGateを空にしない。

## 初回置換：Observability

Baseline: `ae68c17ff9db19370067a7aa45f9492a724e63c4`（旧スイートがCanonical CIでPASSした固定Revision）。

| 凍結元 | 旧ケース | 新正本 |
|---|---:|---|
| `tests/runtime/test_execution_measurement.py` | 4 | `tests/runtime/test_observability_contracts.py` |
| `tests/runtime/test_persistence_measurement.py` | 2 | 同上 |
| `tests/runtime/test_model_usage.py` | 4 | 同上 |

旧ファイルは `tests/delete/runtime/` に**元の内容・Blob SHAで**移動しています。新正本は、Metric失敗時の非再実行、Exception原型・秘密情報の非漏洩、型付きToken計測、Immutable Snapshot、失敗Telemetry時の書込保持、Read計測、Token集計、不正Token値の拒否を8ケースで検証します。

比較実行例（開発時だけ。凍結Testは通常のCIスイートに含めない）:

```bash
python -m unittest discover -s tests/delete/runtime -p 'test_*.py' -q -b
python -m unittest tests.runtime.test_observability_contracts -q -b
```

削除する際は、この置換記録と固定RevisionのGit履歴から旧テストを参照できます。新しい正本のPASSを実Unity Editorや実機検証に読み替えません。

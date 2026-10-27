# テスト基盤の責務別再設計・監査実行記録

**Goal:** 添付「UnityAgent｜テスト基盤の全面再設計」のB案に従い、P1の契約・構造・旧移行テストを監査し、最小限の正本へ移行する。

**Architecture:** `unittest` と既存Validatorを直接使う。テスト数ではなく検出する不変条件を比較する。P2以降の統合と実Unity検証は、このP1の完了とは区別する。

**Tech Stack:** Python unittest、既存Schema / Layer / Policy Validator。

**Spec:** ユーザー添付のB案。新規Framework、独自承認機構、未実装機能用Fixtureは禁止。

## 制約と判断

- 既存の承認範囲で可逆なソース編集とローカル検証を実行する。
- Routeは `generic-planning`。`required_policy_clauses` は未指定。User PolicyとApproval Policyを読み、Contextを既存materializerで構築する。
- 新規ファイルのPurpose / Reuse / Separation / Cost / Retirementは、単一Inventoryの `new_files` に記録する。
- 全327ファイルを列挙するが、P1以外は `audit_status: pending` とする。暫定維持を監査済みと表現しない。
- `tests/delete/` は一括作成しない。置換を比較できたファイルはGit履歴を根拠に直接撤去する。

## Review Focus

- Validatorが常に成功する退行を、違反を注入したテストが検出する。
- 現行の承認・Scope・Entry境界を、移行という名前だけで削除しない。
- 新正本をCanonical runnerが実行し、旧正本を二重実行しない。
- ファイル移動後もROOTとimport先が正しい。
- 実Unityの未実行をPython PASSで代替しない。

### Task 1: 契約正本へ移行

**Files:** `tests/contracts/test_core_contracts.py`、`tests/contracts/__init__.py`、`tools/validate_all.py`、旧 `tests/architecture/test_layer_boundaries.py` / `tests/policy/test_policy_migration.py`。

- [x] 対象11テストファイルのBaselineを測定する。
- [x] LayerとPolicyの独自条件を1つの正本へ移す。単なるValidator正常終了の重複と過去の設計文書の文言確認を除く。
- [x] Layerの禁止Edge、Policyの弱体化、EntryのProvider指定、不正Schemaの拒否を既存Validatorで検証する。
- [x] Validatorの検出処理をテストProcess内のpatchで一時的に無効にして比較し、重要な異常系が失敗することを確認する。
- [x] `tools/validate_all.py` で新スイートを登録する。旧ファイルの置換確認後に撤去する。

### Task 2: 単一Inventoryと証拠

**Files:** `docs/migration/test-foundation-inventory.json`、本計画。

- [x] 327ファイルにsource path、protected invariant、replacement path、evidence SHA、runtime cost、decision reason、監査状態を記録する。
- [x] P1の監査済み11ファイルと、未監査の暫定維持を明示する。
- [x] 同条件の対象テストとCanonical local validationを実行し、件数・時間・制約を記録する。
- [x] 差分をレビューし、P2以降・実Unity・AI Tokenの未観測を明示して報告する。

Pre-flight: Task 2はTask 1の新パスと測定結果を参照する。同じInventoryに確定した置換だけを記録する。

## 実行記録

- 旧正本2ファイルの8件は、4件を同じAssertionのまま保持し、3件のValidator重複確認と1件の過去文言確認を撤去した。3件の異常系テストを加え、新正本は7件。
- 対象比較は58件 / 2.552秒 → 57件 / 2.417秒。単回測定であり高速化の一般的保証ではない。
- Layer / Policy / Entry Schemaを常時成功にする3種のMutationをすべて検出した。Productionコードは変更していない。
- Inventoryは基準Commitの327ファイルを過不足なく列挙し、11件を監査済み、316件を暫定維持・未監査として記録した。
- 独立レビューで修正必須の指摘なし。
- 通常SandboxのCanonical検証は、既存Blender Session LockのOSユーザー領域が読み取り専用のため中断。OSのLock namespaceを変更せず追加実行権限で再実行する。
- P2–P4、GitHub CI、実Unity、AI Token計測は今回の完了範囲と区別する。
- Canonical local validationは32 Validator・13スイート、1,124件成功 / 2件skip、225.462秒で成功。skipはWindows JunctionとGolden Artist Fixtureの環境条件。GitHub CIと実Unityの成功を意味しない。

## 継続実行：残る責務の監査・移行

元のB案に従って残る全ファイルの採否を調べる。P1時点の未監査数と測定値は履歴として保持し、同じInventoryに最終判断を追記する。実Unityは実行環境が確認できなければBLOCKEDとし、Fixture・Gateを維持する。

### Task 3: Runtimeと実行Authorityの再編

- [x] `test_execution_measurement.py` / `test_model_usage.py` / `test_persistence_measurement.py` の10件を `runtime/test_observability.py` へ統合し、Telemetry失敗隔離・秘密情報非漏洩・Nullの区別を保つ。
- [x] `runtime/test_control_plane.py` を `control_plane/test_execution.py`、`runtime/test_task_dag_execution.py` を `orchestration/test_task_execution.py` へ移し、利用元のimportとCanonical discoveryを更新する。Fixtureの汎用化はしない。
- [x] Artist Adapter / Capture / Process Bindingは同一Provider Fixtureを使うため `subagent/artist/test_artist_execution.py` へ統合する。Mutation Mapper・Approval・Evidenceの独立した拒否系は維持する。
- [x] 各旧テストのAssertionと検出対象を比較し、対象スイートを実行する。

### Task 4: Eval・Persistenceと残る契約

- [x] 実装済みSpecialist比較とPromotion比較を同じ正本へ統合する。BaselineとCutoverの比較も同じComparatorの正本へ統合し、Helper名の衝突を避ける。
- [x] Persistenceの空走査を再現し、実在するlowercase sourceとAST importを確認するよう修正する。禁止import注入と空ツリーの拒否も確認する。
- [x] Artist / Graphics等のRoute選出を同じルーティング正本へまとめる。直接実行時に後半クラスが欠落する既存のunittest.main位置を修正する。
- [x] 残るFixture・C#・配布・実Editor Gateは実行環境と故障原因で評価し、根拠なく統合・撤去しない。

### Task 5: 最終証拠

- [x] 全327ファイルの監査結果を同じInventoryに反映し、提案と実施済みの置換を区別する。
- [x] 新規ファイルの5項目、検出比較、実測、実Unityの利用不可を記録する。
- [x] Canonical local validationとCIで明示実行されるUnity EvidenceのPython検証を実行する。実Editor / PlayMode / Deviceとは分けて報告する。
- [x] 独立レビュー後に変更と証拠をコミットする。危険な拒否系が同等であることを確認した旧ファイルだけを撤去する。

## 全体監査・移行結果

- 全327ファイルを内容監査し、未監査は0件。REUSE 121 / RETAIN 150 / CONSOLIDATE 20 / REMOVE 9 / BLOCKED 27。BLOCKEDはC#実行環境・実Unityの不足であり、未読や削除候補ではない。
- `tests/` の追跡資産は327 → 308。UnityのScene・GUID・Assemblyを維持し、固定18ファイルへの集約は行っていない。
- 移行した22ソース・176テストメソッドはAST同等。Fixture Module参照とCutover Helperの名前変更だけを正規化して比較した。
- Telemetry 3 → 1、Artist Provider境界3 → 1、Route選出2 → 1、専門登録とCandidate契約5 → 1、Context Map/Migration 2 → 1、Specialist比較2 → 1、Baseline/Cutover比較2 → 1。Control PlaneとTask DAGはAuthorityに合う既存Suiteへ移した。
- Persistenceは旧検査が空走査になることを再現し、絶対・相対Import/ImportFromの5形態と空ツリーを拒否することを確認した。
- C# Entry 2件の継承重複4件と、実Builder検査より弱い手書きTrace smoke 1件を除去。重要な拒否系を件数削減のために撤去していない。
- Canonical local validationは32 Validator・14スイート、1,119件成功 / 2件skip、213.501秒。P1単回値225.462秒との差は測定環境のばらつきを含み、速度改善率として主張しない。
- CIが別途実行するAuthority source検査2件とUnity Evidence検査59件は、それぞれ2件成功、57件成功 / 2件skip。Artist Backend、Unity Fixture、Portable Pathの静的Gateも成功。実C#コンパイル・Unity Editor・PlayModeの成功とは区別する。
- Portable Path Gateが見つけた固定PC Pathは、実行機械の説明と汎用Windows Fixture Pathへ修正。Installer 18件を再確認した。
- 実Editor、Unity CLI、.NET、PowerShellが利用不可。GitHub CI・実Unity・Player・Target Deviceは未観測。実行を必要とする27 C#ファイルは置換せず既存Gateとともに維持した。

## 監査提案と実施判断

- 監査担当のSplit/Merge提案は採用決定ではない。最終判定は単一Inventoryの `decision` / `decision_reason` / `migration_action` とする。
- Operationsの実Gateway/保存検証、AdmissionとProvider実行、PerformanceとWorld Planningの固有Dataset、異なるTask Scheduler APIは、失敗原因・Fixtureの差を理由に独立維持する。新しい共通FixtureやFrameworkを導入してファイル数だけを減らさない。
- 手動Routing Corpusの固有Policy拒否例を保存する。自動実行の消費元がないことを明記し、自動テスト件数へ含めない。
- `artist-e2e/Assets/.keep` は配布Source Manifestで固定されているため維持する。実Unityが使えない段階で配布Snapshotだけを変更しない。
- `tests/delete/` へのコピーは増やさず、同等性確認済みの旧テストと未参照の旧Backend SnapshotはGit履歴へ退役した。

- 最終独立レビューで未解決の指摘なし。相対ImportFromも拒否する追加強化後にPersistence 35件を再実行して成功、禁止依存5形態と空走査の6 Mutationを検出した。

## 最新mainとの統合

実行中にmainが `ab8a4ffcbf6d92d598a3bf38c8b8626c43e588e5` へ進んだため、Test Lifecycleと既存Observability 8件の正本を取り込んだ。独自の10件版を削除して既存正本を再利用し、凍結3 Blobの同一性、旧10件・新8件の成功、全不変条件の対応を確認して凍結ファイルを退役した。最終AST比較の対象はObservabilityを除く19ソース・166メソッド。テスト追跡資産は移行手順READMEを含め309件。Main由来のPolicy / Skill / Skill Evalは維持する。

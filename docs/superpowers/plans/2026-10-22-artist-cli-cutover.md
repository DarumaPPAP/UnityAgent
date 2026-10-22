# Artist Host CLI段階移行の実装計画

目的：ArtistSubAgentの公開3操作と内部9コマンドを維持し、既存Unity CLIへ統合した後に独立Hostを撤去する。

構造：UnityAgentのControl Plane、Approval、ToolBroker、Dispatcher、Persistenceを再利用する。Artist固有の型付きAdapterは既存`unity_cli`配下に置く。別の承認Authorityや実行基盤を追加しない。

仕様：利用者提供の「UnityAgent — Artist Host CLI廃止・Unity CLI統合仕様書」と「UnityAgent — Artist Host CLI撤去・Unity CLI統合 実装指示書」。この計画はその段階移行と停止条件を実行用に整理する。

## 全体制約

- `artist_subagent`、`subagent/`、Editor Package ID、Namespace、GUIDは維持する。
- `domain.workflow`のSafety / Evidence要求5/5を弱めず、`unity_cli`の4/4を証拠なく引き上げない。
- 直接Pipeline呼出しでも偽承認・Scope超過・古いRevisionを拒否する必要がある。
- 実Editor Gateが未通過なら旧Host、Installer、Setup、配布物を削除しない。
- `BLOCKED_NOT_RUN`と`not_observed`をPASSにしない。Merge、Release、Tag、Archiveは実行しない。
- Developmentは同一レビュー済みSHAで照合する。外部Unity CLIの製品Versionは別に記録する。

## 契約と比較Baseline

- [x] 最新mainと既存差分を確認する。開始SHAは`84eade0868c403b440a4d7db86b21cfa98c731a0`。作業前の未コミット変更はない。
- [x] `unity_artist_cli`参照を現役依存、互換Fixture、履歴、文書に分類する。
- [x] `test_artist_cutover_baseline.py`を先に追加し、未作成Fixtureで失敗することを確認する。
- [x] `tests/runtime/fixtures/artist-cutover-baseline.json`に型付き入力、Editor結果例、現行MapperのEvidence、外側失敗の分類を固定する。FixtureはSource由来の合成データと明記する。
- [x] `test_reference_implementation.py`で非空の偽承認ID、期限境界、別Run／Projectへの流用を拒否する。
- [x] `test_control_plane.py`でContext Receiptの欠落・異なるID・異なるFingerprintを拒否するテストを追加する。
- [x] 必須の既存静的・Unit・Packaging・Host契約検証を実行し、環境阻害を個別記録する。全体は`82ffaa724175b5f31c2b5ab4056f3a99eb2c676d`のCIログで通過を確認。実Editorは未観測。

## 既存Unity CLIへの接続

- [ ] `unity_cli`配下で9コマンドの型付きAdapterを実装する。`build_pipeline_command()`とCommand Discovery、既存Dispatcherを再利用する。
- [ ] Command Catalog、EditorのProject、Package、Render Pipeline、Revision、Scopeを実観測で照合する。
- [ ] 既存Approval Authorityへの最小検証インターフェースを設計し、実行直前にPlan、Exact Diff、Run、Project、Revision、Scope、有効期限、取消、再利用を照合する。
- [ ] 直接Pipeline Mutationがこの検証を迂回できないことを確認する。真正性を検証できない場合は変更コマンドを利用不可とし、Mutation切替を停止する。
- [ ] Editorの構造化結果、Context Receipt、CaptureのCamera・Path・Hashを照合するMapperを追加する。Evidenceの補完は禁止する。
- [ ] 5/5の契約を証明してからRegistry／ResolverとSubAgent適格性を移す。Optional Installationと`auto_install: false`を維持する。

## 実Editor検証と撤去

- [ ] 独立コピーしたUnity 6 FixtureでInspect、Plan／Preview、Capture、Human Review／Refine、承認Apply、Exact Diff／Undo、Timeline、拒否系、Domain Reload／再起動を検証する。
- [ ] 旧Hostなしで同じ経路を実行する。画像取得とVisual受入を分離する。
- [ ] 必須実Editor Gate通過後に限り旧Provider、Host、専用Probe／Installer／Setup、Release生成を撤去する。
- [ ] 旧Evidence、Snapshot、Source Lock、Offline Importの互換Fixtureを保持する。
- [ ] 同一レビュー済みSHAのArtifact照合、P9のUnity 6000.3.12f1／URP 17.3.0、Production G1を独立検証する。

## レビュー重点

外側CLI成功とEditor成功の混同、Plan／RefineからのMutation Evidence捏造、Context ReceiptのHost受信とEditor受信の混同、CaptureとVisual受入の混同、承認IDと認証済み承認Decisionの混同を確認する。

実行方法：このセッションで順に実施する。既存の段階計画の停止条件を優先し、未実行Gateを越えて変更を接続しない。

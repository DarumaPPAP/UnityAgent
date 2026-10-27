# Artist Host CLI移行前の契約と阻害条件

## 対象と判断

調査対象は`DarumaPPAP/UnityAgent`の`84eade0868c403b440a4d7db86b21cfa98c731a0`。最新mainを取得し、依頼記載のSHAと一致することを確認した。初期Checkoutの`f16362290030ed03f8d569775eec36a40da00b97`からの差分はSetup Windowの接続Dashboardのみであり、その変更を維持した。

この変更は移行前の比較Fixtureと回帰テストを追加する段階である。**Mutation経路の切替と旧Hostの撤去は停止している。** 既存Editorに承認真正性の検証経路がなく、必要な実Editor Gateも未実行である。ArtistSubAgent、現役Provider、Setup、Installer、Release、履歴は変更しない。

## 参照の分類

[当時の参照一覧](https://github.com/DarumaPPAP/UnityAgent/blob/806783ced882494a238de770eeda82502f53af6a/tests/runtime/fixtures/artist-cutover-inventory.json) は上記SHAの追跡済みファイルに対し、`unity_artist_cli`、`unity-artist`、`UnityArtist.Tools.csproj`、`UNITY_ARTIST_CLI_PATH`を検索した結果である。検索語に一致しない推移的依存まで網羅するものではない。

| 分類 | 主な対象 | 扱い |
|---|---|---|
| 現役依存 | Provider、Environment Discovery、Registry、Control Plane、Catalog／Manifest、Installer、CLI、Runtime Schema、Setup Window | 切替の検証後に更新する |
| 現役配布・検証 | `release-tag.yml`、`validate-agent-contracts.yml`、HostのProject／Install Script、Package Verification Mirror、Packaging Test | Host撤去前に代替検証を用意する |
| 互換Fixture | `tests/runtime/fixtures/artist-consumer-v1.yaml`とHub Catalog Snapshot群 | 一括改名・削除しない |
| 履歴 | `tests/unity/evidence/artist/historical/`、Migration、Decision、過去監査 | 当時のProvider名・SHA・観測範囲を保持する |
| 説明文書 | Artist境界、環境適応、Capability状態、Host／SubAgentのREADME | 実装状態に合わせて更新する |

現役の専用互換Readerへ旧IDを閉じ込めた状態ではない。Snapshot Schema、Catalog Importと過去ProviderResultの読取にも旧IDが現れるため、Runtime経路の撤去と履歴の読取維持を分けて扱う。

## コマンドと公開操作

公開操作は`artist.camera.inspect`、`artist.camera.refine`、`visual.capture`の3つ。RuntimeのTool Capabilityは`domain.workflow`と`visual.capture`であり、以下の内部コマンド9個を公開Capability9個へ拡張しない。

| 内部コマンド | 入力の要点 | 移行で照合する結果 |
|---|---|---|
| `artist.inspect` | 明示Project、現在Catalog | 対象と対応Pipeline、変更なし |
| `artist.plan` | `request-json`、`expected-revision` | Plan ID、Exact Diff、Revision |
| `artist.preview` | `plan-id`、`expected-revision` | 同一Plan、変更なし |
| `artist.apply` | Plan、Revision、承認参照 | 実Diff、Undo、非自動保存 |
| `artist.capture` | Cameraを束縛した`request-json` | Capture ID、画像Path／Hash、Camera |
| `artist.evaluate` | Capture、明示的な人間のDecision | 評価ID、Human Review |
| `artist.refine` | Evaluation、変更Intent | 元評価に結び付いた再計画 |
| `artist.history` | 明示Project | 制限された履歴 |
| `artist.cinematic` | `inspect / plan / preview / apply`と操作別引数 | Timeline対象、Plan、Diff、変更時承認 |

[比較Fixture](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/fixtures/artist-cutover-baseline.json) はSourceから作成した合成例であり、9コマンドとCinematicの4操作を含む。実Editorから採取したGoldenや、有効な承認Token、Capture画像ではない。`current_evidence`は旧Mapperの挙動の比較値であり、移行後の成功要件ではない。既知の過剰申告を新Mapperへ移植してはならない。

## 既存経路の責務と再利用先

Hostの`Program.cs::ExecuteArtistCommand`はUnity Project／Version／Pipeline対応の検査、Context Manifest読取、Apply時のPlan ID／非空Token／Revision検査、入力オプションの転送、外側CLI結果の変換を担う。`workflow`はHost側で消費され、Pipelineへ転送しない。`context-manifest-path`もHost側で読み、Editor Commandの引数には含めない。

Hostが返すContext Receiptは、`materialized_context.context_id`と`context_fingerprint.value`を読んだことの申告である。現在のEditor Commandがそれを受け取った証拠ではない。Control PlaneではProvider申告のID／Fingerprintと生成Contextを照合する。Hostを外す際はこの受信境界を明示し、リクエストから値をコピーしただけで受信済みにしない。

既存Unity CLIの`discover_unity_cli_surface()`、`extract_command_catalog()`、`build_pipeline_command()`、`DispatchRequest`／`dispatch()`を再利用する。DiscoveryはCLI Version、製品コマンド、Project Info、Status、Pipeline到達性、Command Catalogを観測する。既存`scene.inspect`のAllowlistをArtistの任意コマンド実行へ広げない。`runtime_only`の拒否、対象Editor Project、Artist Package、対応Pipelineの照合はArtist Adapterの追加要件になる。

## 切替を止める安全性の欠落

1. `ArtistSession.Apply()`と`Cinematic(..., "apply", ...)`の承認判定はTokenの非空チェックである。Plan／Revision確認は存在するが、既存Approval StoreのDecision、失効、取消、Run／Project／Scopeと結び付いていない。直接`unity command artist.apply`の呼出しがPython側の承認検証を通る仕組みは確認できない。
2. `ApprovalDecisionResolver`と`RuntimeDispatchGate`は既存Control Plane側の信頼境界として再利用できる。ただし、現在のEditorにはこのAuthorityへ認証された問い合わせを行うインターフェースがない。安全要件を満たすまで新経路の変更コマンドを利用可能にしてはならない。
3. 旧`normalize_artist_result()`は外側`status: passed`を優先する。内側Editor結果を`status: failed / APPROVAL_REQUIRED`にした合成入力でも、実際の返値は`passed`、Evidenceは`domain_result, mutation_evidence`になった。これはHost単体の終了コードや外側成功をGateに使えない理由である。
4. 旧Mapperは空の`refine`成功Payloadにも`mutation_evidence`を付与した。`cinematic`のInspect／Planにもコマンド名由来のMutation Evidenceが付く。Refine／Planは変更の実証ではない。
5. 現行Receiptの包装形と、Hostの`backendResult`を伴う包装形は同一ではない。新MapperはEditorの結果を厳密に読む必要があり、欠損・不正JSON・不明Status・必要Evidence欠落を拒否する。
6. Capture結果はCamera名と画像Pathを返すが、全操作のMapperが実ファイルHashを照合する契約にはなっていない。画像取得をHuman Visual Acceptanceへ変換しない。

必要な最小検証インターフェースは、既存Control PlaneのAuthorityへRun／Project、Capability／操作、Plan ID、Exact Diff digest、Revision、Asset／Component／Property、Scopeを渡し、有効期限・取消・使用済み状態を実行直前に照合するものとする。Editorで別の承認StoreやAuthorityを作らない。既存Bridgeの認証された通信、失効反映、実行と一回性の保証が未確定であるため、この報告を実装済みの認証設計と扱わない。検証不能時の結果は変更不可である。

## Resolverの強度と選出条件

| 対象 | Safety | Evidence | Priority |
|---|---|---|---|
| `domain.workflow`要求 | 5 | 5 | 該当なし |
| `unity_cli`宣言 | 4 | 4 | `project.inspect` 70、`scene.inspect` 60、`profiler.observe` 90 |
| `unity_artist_cli`宣言 | 5 | 5 | `domain.workflow`／`visual.capture` 140 |

Artist ProviderはDomain／Workflow Qualifierを持ち、適格性はavailable、compatible、project_bound、package_installed、pipeline_reachableがすべてtrueの場合に限る。未知のFactをtrueと推測しない。Optional Installationと`auto_install: false`を維持する。

強度5/5はRegistry宣言であり、上記安全性の欠落が解消したことの証明ではない。要求値を4/4へ下げたり、Unity CLI全体を根拠なく5/5へ上げたりして切替を成立させない。

## 検証と未観測範囲

実行コマンドと確定結果は変更申請本文にも記録する。初回のPython単体実行はPackage Resource未生成で失敗し、既存の`python setup.py build_resources`実行後にArtistの既存13テストが通過した。Productionコードを変更する必要はなかった。

| Gate | 状態 | 理由・証拠 |
|---|---|---|
| 移行Baseline・Artist・Approval境界の対象Unit | PASS | 31テスト。合成入力／Python内の検証でありEditor実証ではない |
| Packaging | PASS | 31テスト。生成された未追跡Python Bytecodeを除去し、`PYTHONDONTWRITEBYTECODE=1`で再実行 |
| Catalog／Registry／Unity Fixture構造 | PASS | 既存の3検証コマンド。Fixture検証はStaticのみ |
| 全体`tools/validate_all.py` | PASS（CI） | `82ffaa724175b5f31c2b5ab4056f3a99eb2c676d`の[CIログ](https://github.com/DarumaPPAP/UnityAgent/actions/runs/39798719602/job/119892980586)で全Validatorと全Suiteの通過を確認。Runtime 623テスト、ReferenceImplementation 42テストには既存の条件付きSkip 1件がある |
| Control PlaneのReceipt回帰 | PASS | Sandbox外で欠落／不一致IDとFingerprintの4入力を検証。Windows上の実行は未観測 |
| Environment／Installer／Unity CLI対象Unit | PASS（CI） | 初回Sandboxの84テストは83 PASS／1 FAIL。Environment／Installerの30テストはローカルで再実行し通過。Profilerを含む全RuntimeはCIの623テストで通過 |
| 旧Host Compile | PASS | 一時導入した.NET 8.0.426でReleaseビルド成功、警告／エラー0。Sandbox内の`NuGet-Migrations` Mutexエラーを避け、Sandbox外で検証 |
| 旧Host契約 | PASS | ローカルとCIで既存11テストが通過。Editor実証とは別 |
| Windows／CI契約 | PASS（範囲限定） | ローカルの55テスト中53 PASS／既存Skip 2。CIのWindows Project Leaseも通過。Artist Receiptの実Windows実行と実Editorは未観測 |
| Unity Compile／Editor Read-only／Mutation E2E | BLOCKED_NOT_RUN | 実Unity Editorと接続可能なUnity CLIがない |
| 旧Hostなしの実Editor実行 | BLOCKED_NOT_RUN | 新経路の切替前、かつ実Editorなし |
| Visual／Performance／Player／実機 | not_observed | 画像、評価者、比較可能な実測、実機証拠がない |
| P9 Release／Production G1 | BLOCKED_NOT_RUN | 必要な実Editorと同一レビュー済みSHAの成果物照合が未完了 |

新旧の処理時間、実プロセス起動数、Token消費、失敗率は未計測であり改善を主張しない。Source上の起動構造と実測回数を混同しない。現在の作業SHAはレビュー済みSHAではなく、今後の実検証にはレビュー済みSHAとArtifact Provenanceを固定する必要がある。

初回Sandbox実行ではHost共有Leaseへの書込制限があり、.NETにもOS Mutex制限があった。Productionの安全境界を弱めず、対象テストとHostビルド／契約はSandbox外で検証した。ローカル全体再実行は同じコードSHAのCI成功を確認してから中断した。中断したローカル全体をPASSとは記録せず、全体成功の根拠は上記CIログとする。最終の文書更新Commitはこのコード検証SHAと区別する。

独立レビューで、合成結果の共通Revision／Undo、承認・Diff・診断Evidenceの不足、およびFingerprintを一時ディレクトリ名へ含めるWindows互換性問題を修正した。Fixtureの不一致を検出する追加テストの失敗を確認してからデータを修正し、対象31テストを再実行した。

## 再開条件

既存Authorityの最小検証インターフェースと、直接Pipelineの偽Token／別Plan／別Project／古いRevision／取消／Scope超過／再利用拒否が成立するまでMutation切替を停止する。5/5の根拠と新経路のContract Testを揃え、独立コピーの実Unity 6 Fixtureで必要Gateを通過してから、旧Hostの撤去を再開する。過去Release、Tag、Evidence、Source Lock、互換Fixtureは書き換えない。

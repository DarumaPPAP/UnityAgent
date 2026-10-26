# Artist機能のUnity CLI完全統合 設計案

状態：利用者が既存Adapter方式と残る設計判断の委任・実装を2026-10-24に承認。実装中。移行全体の完了・Production切替成功を意味しない。

対象正本：`6288cd106614913e0466a71ed539fe11ea5c0411`。2026-10-24にGitHubのmainを照合した。

## 目的と完了条件

ArtistSubAgentのInspect、Plan、Preview、Apply、Capture、Evaluate、Refine、History、Cinematicの9コマンドを、既存Unity CLI ProviderとPipelineだけで実行する。CinematicはInspect／Plan／Preview／Applyをすべて含む。旧Provider、独立Host CLI、Host導入・探索・選出・配布へのProduction依存をゼロにする。

Control Planeを唯一のApproval Authorityに保つ。既存Policyの安全性・Evidence要求を弱めない。過去Evidenceと互換Fixtureは保持する。Merge／Release／Tagは別途明示指示があるまで実行しない。

全コマンドの実Editor回帰、承認拒否、HostなしE2E、UPM／Control Plane／開発配布物のRevision照合が成功した時点だけを完全統合完了とする。未実施は`BLOCKED_NOT_RUN`、未観測は`not_observed`とする。

## 方針と選択肢

採用方針は、既存`unity_cli/artist_command_adapter.py`と`artist_result_mapper.py`を拡張し、既存Discovery、Dispatcher、ToolBroker、Approval Store／Resolver、Persistenceを再利用する方式。2026-10-24に利用者が「既存Adapterを拡張して進める」を選択した。

独立HostをUnity CLIの内側から起動する案は、Host依存ゼロの完了条件を満たさないため採用しない。Unity CLIとは別のArtist Providerを新設する案も、Provider一本化の要求と重複実装回避に反するため採用しない。

## 現行実装から判明した制約

- `UnityCliProvider.run_artist_read_only()`はProduction非接続の検証入口。`scene.inspect`のreadのみでInspect／History／Cinematic Inspectに限定される。
- AdapterはApplyとCinematic Applyを無条件に拒否する。Plan／Previewはargv構築と変換だけが実装され、検証入口からdispatchできない。
- Result MapperはCapture／Evaluate／Refineを拒否する。Context Receiptは期待値が渡された場合に照合するが、Editorの現行Pipeline引数にはそのContext受領経路がない。
- Editorの`ArtistSession.Apply()`とCinematic ApplyはTokenの非空判定しか行わない。Python側の承認Resolverの検査だけでは、直接Pipeline呼出しを防げない。
- `ToolBroker._subagent_provider_gates()`はProvider単位でSubAgent適格性を除外する。Artistを単純に`unity_cli`へ付け替えると、Artist未導入時に汎用Unity CLI操作まで除外する可能性がある。Capabilityと専門Agent要求の組合せへ限定する修正が必要。
- `domain.workflow`は既存PolicyでMutationとEvidence 5/5を要求する。Read-onlyを同Capabilityの成功として接続するために要求を下げない。

## 実行境界

最終経路はEntry → Control Plane → Policy／Context／専門Agent適格性 → ToolBroker／Resolver → UnityCliProvider → 型付きArtist Adapter → Unity CLI → Pipeline → Editor → Result Mapper → Persistenceとする。

汎用Unity操作の適格性はArtist Packageの有無に依存させない。Artist機能だけはArtist Package、互換性、Project Binding、Catalogの対象コマンド、Pipeline到達性を実観測で要求する。未導入や不明を自動インストールで補わない。

Read-onlyは既存のread Policyで許されるCapabilityと操作だけで選出し、PlanをMutation完了に昇格しない。公開操作と内部9コマンドを混同しない。新たなread契約が必要な箇所はPolicyとSchemaを同時にレビューし、既存`domain.workflow`の制約を置き換えない。

## Mutation承認境界

Editorは承認を発行しない。Control Planeの信頼済み承認StoreとResolverがDecisionを確認し、実行直前の照合要求を処理する。引数に非空Tokenがあるだけでは実行しない。

照合対象はProjectの正規化Identity、Run、Task／契約Digest、操作、Plan ID、Scope、base／expected Revision、Exact Diffの正規化Digest、有効期限、取消世代、単回実行ID。受信したContext ID／FingerprintもEditor結果へ明示的に束縛する。

Editorが再計算したRevision／Exact Diffを照合し、承認の単回消費をControl Plane側で原子的かつ永続的に予約する。通信失敗、未知の承認、期限境界、取消、競合、異なるProject／Run／Plan／Diff、使用済み予約はScene変更前に拒否する。

承認予約からScene変更までを1つのEditor処理単位に収める。変更開始後の通信断やEditor停止は結果不明として記録し、自動再試行をしない。元の予約を再利用可能へ戻さず、再実行には再観測と新承認を要求する。部分変更を成功として返さない。

直接`artist.apply`と`artist.cinematic --operation apply`、内部Session API、Batch入口を同じ照合点へ集約する。通常入口だけの検査や、Hostでの検査をEditor受領済みと扱う実装を禁止する。

### 確定した実装判断と残る契約

初期mainにはEditor向け認証サービスがなかったため、既存Resolverを使う短命の`ArtistAuthority`を実装する。Control PlaneがProjectの固定Libraryパスへ排他的に作るdescriptorを信頼アンカーとし、256-bit secretによるraw UTF-8 request／responseのHMAC、nonce、sessionを検証する。外部URL、任意検証delegate、引数からのdescriptor差替えは公開しない。

取消と単回消費は同じApproval StoreのOS file lockで直列化する。Resolver→Storeのlock順序を統一する。消費Record保存を開始の確定点とし、それ以前の取消を拒否し、それ以降の失敗・通信断では承認を未使用へ戻さない。Domain Reload後もdescriptorのsessionを照合し、既存descriptorを自動上書きしない。

初期のTypedActionは単一のCamera数値変更を対象としていた。現在は、一般Artist Planを同一Control PlaneのApproval Storeへ不変の `artist_plan_approval` として保存し、複数変更とCinematicを承認する。単値TypedActionへ一般Planを偽装しない。Exact Diff、全mutationPaths、Project／Run／受領Context、期限／取消状態を承認Digestへ含め、実行直前にも再検証する。

Editorに一般的な承認Store書込権限を公開しない。同一ユーザーによる任意ファイル改竄・任意C#実行へのsandboxと、bounded CLI／Pipeline経由の偽承認拒否は別の脅威として記録する。一般Mutation契約とBuilt-inの実Control Plane E2E成立後に旧Hostを撤去した。全体のDoDは実環境マトリクス等の残るGateを含めて別途判定する。

## 結果とEvidence

外側CLI成功とEditor内部成功を個別に確認する。既存Schema 2.0、command、Project、Unity／Render Pipeline、Plan、Revision、Diff、Context Receiptの整合性を検査する。新規Receipt項目はバージョンを明示し、履歴データの読み取り互換とProduction必須条件を分ける。

Captureは明示Camera Binding、許可された保存先、ファイル実体、バイト数、SHA-256を照合する。Captureの存在だけでVisual Acceptanceを生成しない。EvaluateはControl Planeで確認されたHuman Decisionへ束縛する。Refineは元のCapture／Evaluationとの連鎖を保持し、計画をMutation Evidenceとして扱わない。

必要なEvidenceはPersistence append成功後だけをdurableと扱う。保存失敗、部分変更、取消、応答欠落を成功へ変換しない。

## 依存関係の移行と撤去

1. Artist SessionとPipeline登録は維持し、承認照合と実際のContext受領を実装する。Package ID、Namespace、GUIDを維持する。
2. Unity CLI Providerで9コマンドを実行し、旧Providerの対応操作を停止する。未移行操作へ暗黙Fallbackしない。
3. Provider Registry、実体生成Registry、ToolBroker、SubAgent Catalog、manifest、backend契約、環境SchemaとDiscovery、Setup要求／Receipt Schemaを同時に整合させる。
4. Host専用`unity-artist`探索、`UNITY_ARTIST_CLI_PATH`、InstallerのHost製品、Setup表示、Releaseのdotnet publish／zip、Host csproj／Program／スクリプトを撤去する。
5. `setup.py`のResource収集、Verificationミラー、Source Lock、Package metadata、CI・Validator・回帰テストからProduction依存を撤去する。ミラーは正本から再生成する。
6. 現行稼働定義から`unity_artist_cli` Provider IDを除去する。履歴Evidence／互換Fixture内の同IDを保持し、Resolverへ再登録しない。

## 検証と切替Gate

| Gate | 必須検証 | 不成立時 |
|---|---|---|
| 基準 | 9コマンドとCinematic各操作の入力・結果・失敗分類、現行回帰 | 原因調査し、成功Baselineを更新しない |
| Read-only | 専用FixtureでInspect／Plan／Preview／History／Cinematic非変更操作、Project切替・取消・Receipt拒否 | 該当操作の切替を停止 |
| Capture／Review | Camera、Path、Hash、Human Decision、Refine連鎖 | Evidence広告を停止 |
| Mutation | 正規承認Apply、Undo、非保存、Exact Diff、通常とCinematic | Mutation切替を停止 |
| Security | 偽造、別Project／Run／Scope／Revision／Diff、期限、取消、再利用、競合、直接Pipeline、Reload／再起動、通信断 | 承認境界を修復 |
| 撤去 | Hostをインストールしない環境で全機能E2E、旧Provider生成／選出／実行ゼロ | 撤去Gate未通過 |
| 配布 | wheel／UPM／Plugin／Verification／CLI Development Revision、全回帰とCI | Release資格なし |

各Gateは実行SHA、Working Tree差分、Package Lock、CLI Version、Editor Version／Pipeline、Fixture Identity、ログHashを記録する。検証後の関連変更は再検証する。

## 実環境の観測

対象Project `D:/Unity_project/MyURPLaboratory`はUnity `6000.3.2f1`、URP `17.3.0`。UPM lockのUnityAgent SHAは上記mainと一致した。Unity CLIは`1.0.0-beta.14`で更新なし。

`unity pipeline list`で対象Projectの起動を観測したが、Pipelineは未導入で到達不可。`unity status`の結果だけを根拠にEditor停止とは判断しない。既存SceneをテストFixtureとして保存・閉鎖・改変しない。

チェックイン済みArtist E2E FixtureはUnity `6000.6.0f1`とPipeline `0.6.0-exp.1`を要求する。実際に使うEditor／Pipelineと一致させた専用コピーを作成し、元FixtureやユーザーProjectを無断更新しない。現時点で実Editor E2E、Security E2E、Hostなし実行、配布Revision整合はすべて`BLOCKED_NOT_RUN`。

## 実装範囲と未完了の扱い

この設計案は移行の成果物そのものではない。承認境界の未確定部分、Production接続、9コマンド回帰、Host撤去、実環境Gateは後続実装の必須対象として残る。Read-onlyのみやAdapter導入のみで作業目標を縮小しない。

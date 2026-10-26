# Artist Unity CLI完全統合 実装計画

> **For agentic workers:** Use superpowers:executing-plans and test-driven-development. 独立したEditor guard／Capture Mapperはdispatching-parallel-agentsで分担する。

**Goal:** 9コマンドをUnity CLIだけで実行し、旧Provider／独立HostへのProduction依存をゼロにする。

**Architecture:** 既存Adapter／Mapper／Dispatcherと承認Resolverを再利用する。Control Planeが検証する短命のProject束縛通信をEditorのMutation直前に照合する。

**Tech Stack:** Python 3.12標準ライブラリ、既存PyYAML／jsonschema、Unity Editor C#、Unity CLI／Pipeline。

**Spec:** `docs/superpowers/specs/2026-10-24-artist-unity-cli-integration-design.md`

## 全体制約

- 2026-10-24、利用者は既存Adapter方式と残る設計判断の委任・実装を承認した。実装方式の再確認はしない。
- domain.workflowの5/5、Approval／Scope／Evidenceを弱めない。旧Host撤去は実Editor Gate後。
- 未実施はBLOCKED_NOT_RUN。Merge／Release／Tagは実行しない。
- 専用cloneとfeature/artist-unity-cli-integrationを使用する。既存D:/UnityAgentとユーザーSceneを変更しない。

## レビュー重点

- 外側CLI成功・内側Editor失敗を成功へ変換しない。
- 偽Token／取消／再利用／通信失敗はScene変更前に拒否する。
- Artist未導入で汎用Unity CLIを除外しない。
- Hostが記録したHashをEditor受領Receiptへ合成しない。
- 新Revision・新差分へ古い検証成功を流用しない。

## Task 1：承認通信と永続単回消費

Files: `src/unityagent/control_plane/artist_authority.py`、`src/unityagent/persistence/approval/approval_store.py`、`tests/runtime/test_artist_authority.py`。

Interfaces: Control Planeで確定したPlan ID／Revision／Exact Diffと既存Task／Approval／Grant／Actionに束縛する`ArtistAuthority`。context manager内だけProjectのLibrary/UnityAgent/ArtistAuthority.jsonを所有する。署名付きHTTPのrequest/response bodyはUTF-8原文をHMAC-SHA256で照合する。

- [ ] 正常・偽造・Project／Run／Scope／Plan／Diff不一致、期限／取消／競合／再利用、descriptor所有権と通信署名のテストを先に追加しREDを確認。
- [ ] 既存Resolverと永続Approval Storeへ再照合・単回消費を実装。取消と実行開始の線形化点は同じ承認File Lock内の消費Record保存。保存前に取消が成立していれば拒否し、保存後の取消は開始済み操作を巻き戻さない。
- [ ] 同テストGREEN、従来Approval回帰を確認。

Ruling: 信頼アンカーはControl Planeが固定Projectパスへ排他的に作成する短命session descriptorと256-bit secret。呼出し引数にendpoint／検証関数を公開しない。bounded Pipeline callerを対象とし、同一OSユーザーの任意ファイル改竄・任意C#実行を防御したとは主張しない。古いdescriptorは自動上書きせず拒否する。

## Task 2：Editor直接Mutation拒否

Files: `subagent/artist_subagent/tools/editor/Editor/Commands/AuthorityClient.cs`、`ArtistPipelineCommands.cs`、`tests/unity/editor/artist/`。

Interfaces: 固定descriptorから`ArtistSession.Apply`／Cinematic Applyの直前に署名付きauthorize要求。request=sessionId/nonce/projectRoot/command/planId/expectedRevision/approvalToken/exactDiff。response=allowed/nonce/sessionId/reason/reservationId。

- [ ] descriptor欠落・偽Token・署名・nonce不一致でScene変更なしをテストしREDを確認。
- [ ] 共通guard、timeout、loopback制約、response署名／nonce／session照合、明示Receiptを実装。
- [ ] 実C#ハーネスとEditor Testを分けて記録。Pipeline／Batchも共通地点を通ることを確認。

## Task 3：全9コマンドの変換と実行

Files: `unity_cli/artist_command_adapter.py`、`artist_result_mapper.py`、`unity_cli_provider.py`、関連runtimeテスト。

- [ ] Captureの実ファイル・Camera・Path・Hash、Human Decision／Refine連鎖、Context受領、承認Receiptの拒否テストを追加。
- [ ] MapperとProviderを拡張。非変更の内部Artist操作は既存read Policyのscene.inspect、Captureはvisual.capture、Apply／Cinematic Applyはdomain.workflowへ対応付ける。Evaluateはreadであっても独立したControl Plane承認を要求する。計画成功だけでdomain.workflow成功にしない。
- [ ] Apply拒否の解除はTask 1/2と実Editor検証成立後。同9コマンド／Cinematic全操作回帰を実行。

## Task 4：Production選出と旧Host撤去

Files: Registry／ToolBroker／Catalog／manifest／Environment／Installer／Setup／Release／Resource収集と関連tests。

- [ ] 専門要求のPolicy検証済みqualifiers.domain/workflowと選出profileに応じた適格性テストを追加。raw argvから専門要求を推測しない。矛盾・未知のArtist要求を拒否しFallbackにも条件を保持。
- [ ] unity_cliへ選出を統合。汎用要求にはArtist適格性を課さず、Artist Adapter入口でも同条件を再検証。
- [ ] 実Editor Gate後に旧Provider／Host／Host Installer／探索／配布を撤去。履歴Evidenceと互換Fixtureを保持。
- [ ] Production参照ゼロ、全回帰、wheel／UPM／CIを確認。

## Task 5：実Editorと配布の最終Gate

- [ ] ユーザーSceneを使わない専用Fixtureを作成。利用する導入済みEditor／Pipeline Versionを記録。
- [ ] Import／Compile／Editor Test、Read-only／Mutation／Security、Reload／再起動、Hostなし全9コマンドE2Eを実行。
- [ ] UPM／Control Plane／開発CLI配布物の同一Revisionを照合。
- [ ] 独立全体レビュー、必要修正と再検証後に完全統合のDoDを判定。

## 進捗台帳

開始SHA 6288cd106614913e0466a71ed539fe11ea5c0411。作業Branchはfeature/artist-unity-cli-integration。Merge／Release／Tagは未実行。

2026-10-24の予備実行ではInspectがdurable Evidenceまで成功し、次Planは新Scope契約のmutationPathsが旧Editor応答にないため安全停止した。この履歴は最終全9成功の根拠に使わない。

2026-10-25時点でTask 1〜4の実装と旧実装撤去、Task 5の導入済みEditorでの検証を実施した。実パスScope照合、受領Contextの実行前照合、Policy判定、Cinematic Director固定、一般LookDevの差分外変更を修正した。最終独立レビューで見つかったCamera／Lightの同名・削除再生成識別、検証例外のUndo、Scope外Scene dirtyも修正し、再レビューの未解決所見は0件となった。上のチェックリストは計画時の作業項目であり、完了判定には最新の[統合検証記録](../../architecture/reviews/artist-unity-cli-integration-progress-2026-10-25.md)とEvidence索引を使用する。

Ruling: Context予算の上限は維持し、Runtimeが既に選出・検証する全Registry／CapabilityRequest Schema／Catalogの重複Context参照を取り除く。専門Capability／Backend／Knowledge／責務境界は保持する。誤って必要情報を除くリスクはContext必須参照テストと全9 E2Eで検証する。

Ruling: headless Editorは公式CLIの状態一覧が空の場合に限り、独立Processの一意なProject bindingと実PipelineのProject・Version観測を用いる。別Project・曖昧・未知Versionは拒否する。誤結合リスクは拒否テストと実Project受領証で検証する。

Ruling: Artist PlanにはEditorが観測した全mutationPathsを保存し、既存Path／Scope検証器でProject/Assetsへの物理的包含、allowed_paths、prohibited_pathsを検証する。承認時だけでなく再解決・実行直前にも再検証し、junction差替を拒否する。受領Contextとpathsは実行認証要求に束縛する。

Ruling: 一般化Planは単値TypedActionへ偽装せず同一Control PlaneのApproval Storeへimmutable Plan approvalとして保存する。明示approveのみが承認を発行し、Policyの既存Capability条件を評価してからBrokerへ進める。

最終コードtree `584a7def1c64df58c4b79a397cbe913ec1e9ce2d` に対して、6000.3.2f1のBuilt-in／URP／HDRP全9コマンド、Cinematic／Volume／Fog Mutation、Editor 34件、再起動後承認再利用拒否、旧Host撤去、UPM内包185ファイルとwheel／Development配布物の同一tree検証が成功した。全Runtimeは715件中失敗9・エラー18・スキップ6で、27問題は開始Commitでも再現しcurrent-onlyは0。Repository固定Version 6000.3.12f1／6000.6.0f1のマトリクスは未導入でBLOCKED_NOT_RUN、Human visual acceptance・性能・LookDev検証例外注入はnot_observed。移行全体のDoDは保留し、Merge／Release／Tagは行わない。

## 残Gate閉鎖の追加作業（2026-10-25）

利用者がEditor追加導入、固定マトリクス、LookDev例外注入、Cinematic全kind E2E、末尾空行修正を明示的に依頼した。Merge／Release／Tag禁止は継続する。上記treeの成功は履歴であり、以下の変更後の成功には流用しない。

- [x] 指摘された5ファイルの末尾空行だけを修正。
- [x] 固定マトリクスの使い捨てProjectへGUID付きScene／metaを運ぶ修正。欠落のRED4件と修正後staging回帰2件を確認。
- [x] LookDev適用後の検証例外を注入。RED1件→GREEN1件。symbol解除後にhook不在を含むEditor35件成功。
- [ ] 6000.3.12f1／6000.6.0f1を追加導入し、既存7 Fixtureの固定マトリクスを実行。
- [ ] Cinematic全8kindと両shot更新をControl Planeから実Editorへ実行。
- [ ] 最終ソース・配布物・Evidenceを再生成／検証し、独立レビューで追加変更を確認。

Ruling: 例外注入は `UNITY_ARTIST_TEST_FAULTS` を所有Fixtureへ一時設定した場合だけ存在するinternal seamを使う。認可・Undo登録・ApplyIntent成功後の既存try内に限定し、通常コンパイルでfield／呼出しが存在しないことを検証する。公開CLIに注入口を追加せず、承認判定も変更しない。誤ってsymbolが残るリスクは設定解除と通常assemblyのreflection拒否テストで検出する。

Ruling: 固定Editorは既存導入先を置換せず `D:/Unity_project/MyURPLaboratory/.artist-toolchains~` へ公式CLIで追加導入する。CLIがWindows絶対パスをcwdと誤結合したため、同じ専用場所をcwdからの相対指定に切り替えた。導入成功は実executableのVersionと起動結果で確認し、ダウンロード完了だけを成功としない。

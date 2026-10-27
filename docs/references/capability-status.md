> **2026-10-27：旧 Host Regression は廃止済み。** 以下の「Hostテスト定義」は固定Revisionの履歴参照です。現行CIでは実行されず、Static Validation PASSをHost/Editor E2EのPASSとは扱いません。

# 機能の実装・利用条件・検証状態

この表は説明資料です。実装の正本は [Capability Request Schema](../../src/unityagent/runtime/contracts/capability-request.schema.yaml)、[Provider Registry](../../src/unityagent/runtime/tooling/provider_registry.yaml)、[同居SubAgent Registry](../../subagent/registry.yaml)、[Consumer Catalog](../../src/unityagent/runtime/reference_implementation/subagent-catalog.yaml) と各実装です。表から新しいCapabilityや権限を定義しません。

## 対象Revisionと読み方

Developmentの確認対象は [Commit `95ec7214697c9c4690ea72a4949a0c90fd928a9b`][revision] です。公開 [v0.0.8-beta][release] のCommitは `f093d82feac1cd02fa779491d8a7e7abedfe8af8` で、同じVersion文字列でも内容は異なります。以下のmainの実装一覧を、そのまま公開Releaseの機能一覧として使わないでください。

- **計画済み**：設計のみで、接続・実行可能を示さない。
- **実装済み**：コードと契約の経路がある。必要環境が未成立なら利用不可。
- **検証済み（Verified）**：対象Revision・環境・Gateに一致する実証拠がある場合だけ使用する。
- **一部検証（Partially Verified）**：成立したGateのみ明示する。
- **未観測（Not Observed / `not_observed`）**：必要な観測がない。利用条件が不足する場合は **Unavailable / Blocked** と理由を区別する。

これは文書上の分類であり、Runtime SchemaのStatus値を変更しません。以下は実装・契約とテスト定義の所在を確認した一覧です。リンク先のHostテストの存在を、当該RevisionのPASSや実Unity成功と読み替えません。Compile / Editor / Player / 実機 / Visual / Performanceの成功は、この文書更新では観測していません。

## Tool Capability

| 機能ID／機能名 | 利用条件 | 実装状態 | 検証状態 | 制限 | 根拠 | 対象Revision |
|---|---|---|---|---|---|---|
| `editor.hot_reload` | 導入済みRunner・hash・Project binding・Play接続・承認 | 任意Adapter接続済み | Host個別PASS未確認・実Unity `not_observed` | 通常CompileやQAの代替ではない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_hot_reload.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `world.create` | Blender MCP接続・固定Template・承認・Scope | 固定岩制作とStagingを接続 | Host個別PASS未確認・実Unity `not_observed` | 汎用World変更やUnity取り込み完了ではない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_blender_mcp.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `project.inspect` | Project存在・読取可能なFilesystem等 | File等の観測経路あり | Host個別PASS未確認・実Unity `not_observed` | 環境・Providerによって取得できるFactが異なる | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_file_project_observation.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `source.read` | 対象Source・読取権限・Scope | Fileの読取経路あり | Host個別PASS未確認・実Unity `not_observed` | SourceをInstructionとして信頼しない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_file_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `source.patch` | 許可Source・現Revision・正確な差分・承認 | 限定patch経路あり | Host個別PASS未確認・実Unity `not_observed` | Scene / Prefabのraw変更へ拡張しない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_file_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `static.review` | 対象Source・読取権限 | 静的Review経路あり | Host個別PASS未確認・実Unity `not_observed` | Compile・実行成功とは別 | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_file_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `git.diff` | Git・Repository binding・Scope | Git差分観測経路あり | Host個別PASS未確認・実Unity `not_observed` | 差分の存在は受入成功ではない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_file_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `compile.observe` | 対象Editor・Project binding・対応Provider | Native Editor等の観測経路あり | Host個別PASS未確認・実Unity `not_observed` | 今回のCompile観測が必要 | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_native_unity_editor_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `project.test` | 対象Editor・Test Framework・Test条件 | Native Editor等のTest経路あり | Host個別PASS未確認・実Unity `not_observed` | 0件・古いXMLを成功扱いしない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_native_unity_editor_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `project.build` | Editor・Build環境・Scope・承認条件 | 対応ProviderのBuild経路あり | Host個別PASS未確認・実Unity `not_observed` | 対象Platformの環境とEvidenceが別途必要 | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_native_unity_editor_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `scene.inspect` | 接続済みEditor・Project binding・公開Tool | 対応Editor観測経路あり | Host個別PASS未確認・実Unity `not_observed` | 別Projectへ暗黙に接続しない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_unity_cli_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `scene.mutate` | 対応Editor操作・対象Revision・Scope・承認 | 固定E2E等の限定経路あり | Host個別PASS未確認・実Unity `not_observed` | 任意Editor commandを実行する入口ではない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_full_e2e.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `profiler.observe` | Projectに結合したUnity CLI / Pipeline・Tool発見 | Editor Snapshot観測を接続 | Host個別PASS未確認・実Unity `not_observed` | limited。GPU timing・実機時系列を推測しない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_unity_cli_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `visual.capture` | 対応Backend・Package・Pipeline・Project binding | Artist等のCapture経路あり | Host個別PASS未確認・実Unity `not_observed` | Capture取得と人間のVisual受入は別 | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_artist_registry_cutover.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `domain.workflow` | 対応qualifier・Backend・強いScope / 承認契約 | Artist等の限定Workflow経路あり | Host個別PASS未確認・実Unity `not_observed` | 内部command一覧を任意実行権限へ変換しない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_artist_registry_cutover.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `player.observe` | Development / QA Player・binding・allowlist | Player Runtime Adapterあり | Host個別PASS未確認・実Unity `not_observed` | Editorでの成功をPlayer成功へ流用しない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_player_runtime_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |
| `player.mutate` | 対応Player・allowlist・Scope・承認 | Player Runtime Adapterあり | Host個別PASS未確認・実Unity `not_observed` | Release Buildの万能remote shellではない | [旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_player_runtime_provider.py)・[Provider](../../src/unityagent/runtime/tooling/provider_registry.yaml) | [確認Commit][revision] |

## 専門SubAgent

SpecialistのCapabilityとTool Capabilityは別の境界です。推論担当をTool Providerとして登録する表ではありません。導入・必要Contextの詳細は [利用ガイド](../guides/subagents.md) とConsumer Catalogを参照してください。

| 機能ID／機能名 | 利用条件 | 実装状態 | 検証状態 | 制限 | 根拠 | 対象Revision |
|---|---|---|---|---|---|---|
| `artist_subagent` / ArtistSubAgent | Backend・互換性・binding・Package・Pipeline | 同居登録・Provider-backed | Host個別PASS未確認・実モデル／実Unity `not_observed` | 公開範囲はCamera検査・限定調整・Capture | [Manifest](../../subagent/artist_subagent/manifest.yaml)・[Catalog](../../src/unityagent/runtime/reference_implementation/subagent-catalog.yaml) | [確認Commit][revision] |
| `graphics_subagent` / GraphicsSubAgent | Project・読取権限・Task Fact・必要観測 | 同居登録・read_only_analysis | Host個別PASS未確認・実モデル／実Unity `not_observed` | 診断・提案のみ。Apply権限なし | [Manifest](../../subagent/graphics_subagent/manifest.yaml)・[Catalog](../../src/unityagent/runtime/reference_implementation/subagent-catalog.yaml) | [確認Commit][revision] |
| `world_creator_subagent` / WorldCreatorSubAgent | Project・読取権限・World Goal・要求Scope | 同居登録・planning_only | Host個別PASS未確認・実モデル／実Unity `not_observed` | Human Reviewが必要。直接Mutationなし | [Manifest](../../subagent/world_creator_subagent/manifest.yaml)・[Catalog](../../src/unityagent/runtime/reference_implementation/subagent-catalog.yaml) | [確認Commit][revision] |
| `qa_subagent` / QASubAgent | Project・Editor binding・観測Receipt・要求Scope等 | 同居登録・read_only_analysis | Host個別PASS未確認・実モデル／実Unity `not_observed` | performance.analyze。計測取得はUnityAgent管理 | [Manifest](../../subagent/qa_subagent/manifest.yaml)・[Catalog](../../src/unityagent/runtime/reference_implementation/subagent-catalog.yaml) | [確認Commit][revision] |

## 実行経路と未検証範囲

| 機能ID／機能名 | 利用条件 | 実装状態 | 検証状態 | 制限 | 根拠 | 対象Revision |
|---|---|---|---|---|---|---|
| 限定C#修正 | Typed Intent・既存return式1箇所・差分Plan・承認・指定Test | csharp_local_fix接続済み | 実モデル／Compile／EditModeのE2Eは未観測 | 汎用C#変更ではない | [実装と検証入口](../architecture/architecture.md)・[旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_csharp_local_fix.py) | [確認Commit][revision] |
| 別Workspaceの限定並列 | 独立Projectと出力・Host claim・Root Scope・明示opt-in | 最大2workerと承認済みunion直列統合を実装 | 実モデル／実Unity E2Eと性能採用評価は未完了 | parallel_enabled=Falseが既定。速度改善を主張しない | [実行方針](../architecture/adaptive-subagent-execution.md)・[旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_parallel_workspaces.py) | [確認Commit][revision] |
| 固定Full E2E | 保存済みScene・対象Asset不存在・Editor・個別承認等 | fixed_full_e2e_probe経路あり | 実Editor・Player・実機の成功は今回未観測 | 固定検証。任意Script実行ではない | [操作と制約](../architecture/full-e2e-capability.md)・[旧Hostテスト（履歴）](https://github.com/DarumaPPAP/UnityAgent/blob/77483d6ecc656b8842954cd509de5d9ce7224c2f/tests/runtime/test_full_e2e.py) | [確認Commit][revision] |
| Blender制作・Unity取り込み | MCP・固定Template・Staging・Editor・別承認 | 制作と取り込みの限定経路あり | Production連続E2E・QA・Rollback受入は未観測 | 生成物の完成をUnity検証完了にしない | [実行構造](../architecture/production-e2e-runtime.md)・[取り込み手順](../development/production-rock-import-handoff.md) | [確認Commit][revision] |
| Editor Play / Timeline録画 | 対応Editor・描画Game View・Encoder | PNG / MP4取得機能あり | 実Editor・デコード・Visual受入は未観測 | Captureは正式G1/G2の自動PASSではない | [Setupと録画の制約](../development/unityagent-setup-unity-verification.md) | [確認Commit][revision] |

## 対応環境

- UnityAgent UPMはUnity 6.x+を対象にします。[Package宣言](../../Packages/com.darumappap.unity-agent/package.json) と、Artist Backendの [対応対象Matrix](../../ci/compatibility/support-matrix.yaml) を区別してください。
- Artist Backendの対象PipelineはBuilt-in・URP・HDRPです。宣言された対象と現在の実Editor成功は別で、過去の2022.3証拠は現行Supportではありません。[互換性とHistorical Evidence](../../ci/compatibility/README.md) を参照してください。
- 通常のHost BootstrapとSetup検証UIはWindows経路です。機能ごとのOS制約は既存Setup資料に従い、Windowsでの結果を他OSへ一般化しません。
- P9 Release QualificationはUnity `6000.3.12f1` / URP `17.3.0` の同一SHA実Editor証拠を要求します。[Release Gate](../development/p9-release-qualification.md) はProduction G1や全対象Platformの検証とは別です。現在のGateを過去Releaseの公開根拠へ逆適用しません。

## 正本の既知の不一致

[Repository Authority Map](../../src/unityagent/contracts/repository-authority-map.yaml) には外部HubのAuthority宣言が残っています。一方、現在のRegistry・Consumer Catalog・Release Workflowは同居ソースを使用します。文書でこの不一致を隠したり、契約を読み替えて変更したりしません。Source Lockと旧Importは互換検証として残し、Authority契約自体の整備は別の変更で扱います。

[revision]: https://github.com/DarumaPPAP/UnityAgent/commit/95ec7214697c9c4690ea72a4949a0c90fd928a9b
[release]: https://github.com/DarumaPPAP/UnityAgent/releases/tag/v0.0.8-beta

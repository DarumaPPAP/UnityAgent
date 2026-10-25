# Artist完全統合の現行調査

調査日：2026-10-24。対象：GitHub main `6288cd106614913e0466a71ed539fe11ea5c0411`。

結論：完全統合は未完了。既存Adapterの再利用方針は利用者確認済み。実装・Production切替・Host撤去は未実施。本調査や基準テストの成功を移行完了として扱わない。

## 調査対象と正本

GitHubの`git ls-remote origin refs/heads/main`でSHAを取得し、同じmainを専用cloneへ展開した。既存`D:/UnityAgent`は古いmainのため変更しなかった。clone時のWindows長いパス問題は`git -c core.longpaths=true restore --source=HEAD --staged --worktree -- .`で復旧し、同オプション付きstatusで既存ファイル差分がないことを確認した。

AGENTS、User／Approval Policy、Authority Map、Provider Registry、CLI Adapter／Mapper／Discovery、ToolBroker、Control PlaneのCamera FOV経路、Approval Store／Resolver、Editor Session／Pipeline登録、SubAgent manifest／契約／Source Lock、Installer、Release／Validation CI、Resource収集、基準テストを確認した。

現行正本の構成は`src/unityagent/`であり、古いcheckoutの`Runtime/`や`ControlPlane/`を現行mainの実装として扱わない。

## 9コマンドの状態

| コマンド | Unity CLI側の現状 | 残作業 |
|---|---|---|
| inspect | typed argv／厳密Mapper／非接続検証入口 | Production接続、Context受領、実Editor E2E |
| plan | typed argv／厳密Mapperのみ | 公開操作内の計画ステップ接続、実Editor検証 |
| preview | typed argv／厳密Mapperのみ | Plan／Revision照合、実Editor検証 |
| apply | Adapterで無条件拒否 | 認証付き承認照合、単回消費、Mutation E2E |
| capture | typed argvあり、Mapperと検証入口は拒否 | Camera／Path／Hash照合、Capture E2E |
| evaluate | typed argvあり、Mapperと検証入口は拒否 | Human Decision認証、Captureとの束縛 |
| refine | typed argvあり、Mapperと検証入口は拒否 | Evaluation連鎖、計画結果の検証 |
| history | typed argv／厳密Mapper／非接続検証入口 | Production接続、実Editor E2E |
| cinematic | inspectのみ非接続入口、plan／previewは構築・変換のみ、apply拒否 | 全4操作、Timeline Diff、承認、実Editor E2E |

Editorの9コマンド登録は`subagent/artist_subagent/tools/editor/Editor/Pipeline/ArtistPipelineCommandRegistration.cs`。公開3操作と内部9コマンドは別契約である。

## Production依存のつながり

| 領域 | 現行依存と撤去対象 |
|---|---|
| Entry／Setup | `src/unityagent/cli.py`の既定製品に`unity_artist_cli`、UPM Setup WindowのHost状態・導入経路 |
| Installer | `toolchain_installer.py`から`release_installer.py`へHost製品を転送、zip内`unity-artist.exe`を必須として展開 |
| Discovery | `environment/discovery.py`の`probe_unity_artist_cli()`が`unity-artist`を探索、Host応答からArtist Factを組み立てる |
| Resolver／Registry | `provider_registry.yaml`の`unity_artist_cli`が`domain.workflow`と`visual.capture`を提供、専用Environment Keyを要求 |
| SubAgent選出 | Catalog／manifest／backend契約が専用Providerへ束縛。ToolBrokerがProvider単位で適格性を除外する |
| Runtime | 旧Providerが独立HostをDispatcherから起動。Camera FOV Control Plane経路にもProvider IDの固定参照がある |
| Host | `subagent/artist_subagent/tools/host/`のProgram、csproj、install・smoke・verificationスクリプト |
| UPM／Editor | Artist PackageとPipelineは移行後も必要。Batch入口も承認境界に含める。Verificationミラーは正本から再生成 |
| CI／配布 | `validate-agent-contracts.yml`で旧Host build、`release-tag.yml`でHost publish／zip、`setup.py`でHost backend契約をResourceへ収集 |
| 外部メタデータ | `subagent-sources.lock.json`に旧Hubの`cli/artist/UnityArtist.Cli.csproj`宣言。単なる削除ではなく現行Authorityとの整合が必要 |

現行trackedファイル74件の参照とSHA-256を[機械可読一覧](artist-integration-inventory-2026-10-24.json)に保存した。分類は削除許可や到達性の証明ではない。履歴Evidence、互換Fixture、回帰テスト、Production実装を同じ条件で削除してはいけない。

## 安全契約の不足

Editorの`ArtistSession.Apply()`（現行281行以降）とCinematic Apply（497行以降）は、Tokenの空判定だけでApplyへ進める。Pipeline登録はこれらのSession APIを直接呼ぶ。真正なControl Planeの照合なしにAdapterのApply拒否を解除することはできない。

既存`ApprovalDecisionResolver.resolve()`は信頼済みStoreからTask／Run／Project／契約Digest／承認状態／取消世代／期限を照合する。Editorとの認証付き通信は現状未接続。既存`ActionReservationStore`の永続予約と再利用拒否も再利用候補だが、通常／Cinematic双方のPlan／Exact Diffへの束縛と取消の線形化を追加設計する必要がある。

`domain.workflow`のSafety／Evidence 5/5を維持する。Read-only成功のためにMutation Policyを下げたり、計画からMutation Evidenceを合成したりしない。

## 現在状態に対する検証

| 検証 | 結果 | 範囲 |
|---|---|---|
| Artist Adapter／Baseline／旧Provider／Resolution | PASS、45テスト | Unit・合成Fixture。実Editorではない |
| ReferenceContractTestsとRuntime承認再照合／再利用 | PASS、9テスト | 既存Resolver／RuntimeのUnit。Editor直接呼出し拒否の証明ではない |
| mainとProject UPM lock照合 | PASS | どちらも`6288cd106614913e0466a71ed539fe11ea5c0411`。開発配布物全体の照合ではない |
| CLI Version／更新確認 | `1.0.0-beta.14`、更新なし | 外部CLI Version。UnityAgentのDevelopment Revisionとは別 |
| 対象Editor起動 | 観測済み | `MyURPLaboratory` PID 36608、Pipeline未導入・到達不可 |
| Import／Compile／Editor Test | BLOCKED_NOT_RUN | 今回実行していない |
| Read-only／Mutation／Security実Editor E2E | BLOCKED_NOT_RUN | Pipelineと対象Revisionの専用Fixtureが必要 |
| Hostなし全機能E2E | BLOCKED_NOT_RUN | 旧Hostを実行しない統合経路が未実装 |
| 全体回帰／CI／開発Artifact Revision照合 | BLOCKED_NOT_RUN | 対象54テストを全体検証へ昇格しない |

Unit Testコマンド：`PYTHONPATH`に`src`と専用依存フォルダを設定し、Python 3.12で次を実行した。

```text
python setup.py build_resources
python -m unittest tests.runtime.test_artist_command_adapter tests.runtime.test_artist_cutover_baseline tests.runtime.test_unity_artist_cli_provider tests.runtime.test_unity_artist_cli_resolution -q
python -m unittest tests.runtime.reference_implementation.test_reference_implementation.ReferenceContractTests tests.runtime.reference_implementation.test_reference_implementation.MutationRuntimeTests.test_dispatch_re_resolves_revoked_approval_at_runtime_boundary tests.runtime.reference_implementation.test_reference_implementation.MutationRuntimeTests.test_idempotent_replay_and_key_reuse -q
```

初回はPyYAML／jsonschema不足、次にsandbox一時領域ACL、その後に生成Resource不足で失敗した。依存を専用フォルダへ導入し、通常権限と標準Resource生成で解消後、上表の結果を取得した。テスト本体・期待値・Productionコードは変更していない。

導入済みEditorは`6000.3.2f1`、`6000.7.0a2`、`2022.3.22f1`。既存Artist E2E Fixture指定の`6000.6.0f1`は導入済み一覧に存在しなかった。専用コピーのVersion／Pipeline適合性を検証する必要がある。

## 設計レビューと次のGate

[統合設計案](../../superpowers/specs/2026-10-24-artist-unity-cli-integration-design.md)を独立レビューした。次の3点は重要な未決事項として残る。

1. IPCの信頼アンカー、信頼情報の初回登録、Reload後の再接続、永続予約の線形化点、予約後取消の効力。
2. Plan／Preview／History／Evaluate／Refine／Cinematic非変更操作を、公開Capabilityと内部ステップへ割り当てる契約。
3. Artist専門Agent要求を識別する信頼済み入力と、通常Unity CLI操作の適格性から分離する条件。

これらは旧Providerを恒久維持する理由ではなく、統合実装の必須課題である。未解決のまま切替・旧Host撤去を実施しない。統合の最終目標と9コマンドの範囲は変えない。

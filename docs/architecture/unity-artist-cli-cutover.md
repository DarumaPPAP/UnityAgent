# UnityArtistCLI cutover

この文書は、UnityAgentをArchitect / Commander / Loop Owner、UnityArtistCLIをvisual art / cinematicのspecialist Provider（概念上のPlayer）として運用する現行境界を記録します。

## 責務と実行経路

UnityAgentは既存の実行経路を再利用します。新しいPlayer Manager、Player Framework、Provider Registryは作りません。

```text
CapabilityRequest
  -> Runtime Guard
  -> ToolBroker
  -> Resolver
  -> Environment Snapshot
  -> Provider Registry
  -> Dispatcher
  -> Provider Adapter
  -> ProviderResult
  -> Evidence Normalizer
  -> Persistence
```

Artist要求は製品名ではなく意味で表します。

```yaml
capability: domain.workflow
qualifiers:
  domain: visual_art
  workflow: lookdev_refine
```

```yaml
capability: visual.capture
qualifiers:
  domain: cinematic
  workflow: capture
```

`unity_artist_cli` Providerは、明示されたProject Rootと既存のDispatcherを使い、JSON envelopeだけを受け取ります。任意のC#、arbitrary eval、shell文字列、Unity YAML直接編集、暗黙のProject切替は許可しません。

Host CLIの help は二段階で扱います。`unity artist help` と standalone `unity-artist --help` は Artist の help 契約を実行します。インストール済み Unity CLI beta は `unity artist --help` をグローバル help として先取りするため、この形は外部互換性制約としてEvidenceに記録し、Artist help 成功とは数えません。

## Provider facts

Environment Snapshotの `unity_artist_cli` は、次の事実を個別に保持します。

`available`, `version`, `executable_path`, `project_bound`, `package_installed`, `package_version`, `pipeline_reachable`, `unity_version`, `render_pipeline`, `support_tier`, `compatibility_backend`, `capabilities`, `failure_class`, `binding_status`, `bound_instance_id`

`pipeline_reachable` が実測で `true` になるまで、ResolverはArtist Providerを実行可能とみなしません。Registryの存在だけで成功扱いしないことが重要です。

## Legacy境界

旧 `myunitymcp` は履歴互換・移行検証のためRegistryに残しますが、`legacy: true` と `production_enabled: false` を設定しています。現行Resolverの候補ランキングからは除外されます。v1.1.1のタグと旧パッケージ履歴は削除しません。

## 正式Release Matrix

| Unity | Render Pipeline | Support tier | 実行Provider |
| --- | --- | --- | --- |
| 2022.3 LTS | Built-in | primary | Official Unity CLI + Unity Pipeline first |
| Unity 6.x+ | Built-in | primary | Official Unity CLI + Unity Pipeline |
| Unity 6.x+ | URP | primary | Official Unity CLI + Unity Pipeline |
| Unity 6.x+ | HDRP | primary | Official Unity CLI + Unity Pipeline |

2022.3 Built-inは年式を理由に別Backendへ切り替えません。実際のGateでは、インストール済み `unity` CLI 1.0.0-beta.8で `2022.3.22f1` を識別できました。一方、`unity pipeline install` はUnity 6.0以降を要求して exit 1 になりました。この結果は `blocked_by_environment` のEvidenceとして保存し、フォールバックによる成功扱いはしません。

2022.3 URP/HDRP、Unity 2023、URP 14–16は正式Matrix外です。Mutation前に `UNSUPPORTED_RENDER_PIPELINE_VERSION` または相当のtyped failureを返します。

## Artist safety lifecycle

LookDev、Lighting、Environment、Camera、Cinematic、TimelineのMutationは次の順序を守ります。

```text
Inspect
  -> Prepare plan
  -> Exact diff
  -> Expected revision
  -> UnityAgent approval
  -> Apply
  -> Capture / Evidence
```

ApplyはUndo登録を行い、暗黙保存を行いません。Evidenceには少なくともPlan digest、対象、revision、approval、差分、Undo登録、save未実行を含めます。Captureは取得できたチャンネルだけをEvidence化し、未構成のdepth / object-idを実測済みと偽りません。

## Plugin boundary

UnityAgentのPluginは `.agents/plugins/marketplace.json` をMarketplace authorityとして公開します。UnityArtistCLI Pluginは別Repositoryの `.agents/plugins/unity-artist` に置き、skill-only構成とします。どちらにも新しいMCP manifestは追加しません。

Setup skillは `unity --version`、`unity artist version`、PATH導入、`unity artist install`、対象Project指定、`doctor --format json` の順で確認し、Editor licenseや外部認証が必要な場合だけ利用者へ返します。

## Verification entrypoints

- Runtime: `python -m unittest discover -v Runtime.Tests`
- Static/repository: `python Tools/validate_all.py`
- Production runtime: `python Tools/ProductionToolRuntime/validate_production_tool_runtime.py`
- Regression: `python Tools/run_regression_gate.py`
- Plugin schema: `.codex/skills/.system/plugin-creator/scripts/validate_plugin.py`
- UnityArtistCLI contract: `Tests/Release/verify_unity_artist_contract.py`

未観測のUnity Editor / Timeline実機結果は `not_observed` または `blocked_by_environment` として報告します。`implemented_unverified` は完了状態にしません。

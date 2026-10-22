<a id="artistsubagent-boundary"></a>

# ArtistSubAgentの責務境界

<a id="canonical-identity"></a>

## 正式な識別子

`ArtistSubAgent` はUnityのVisual Art・Cinematicを担当する任意の専門Agentです。正本IDは `artist_subagent` です。`unity_artist_cli` は限定されたArtist操作へ接続するBackend Providerの互換IDであり、SubAgentの名前ではありません。

<a id="ownership"></a>

## 責務

UnityAgentが要求の意味、Policy、Approval、変更Scope、SubAgent選出、Loop・Retry制御、永続Evidenceを所有します。ArtistSubAgentは専門的な推論と限定Workflowを担当し、全体のRouting、Policy、承認、永続化を所有しません。Backendは実行だけを担当します。

```text
利用者 / Codex
    ↓
UnityAgent Control Plane
    ↓
CapabilityRequest
    ↓
ArtistSubAgentの適格性確認と計画
    ↓
Backend Provider Resolver
    ↓
unity_artist_cli
    ↓
ProviderResult → Evidence
```

<a id="optional-installation"></a>

## 任意導入と利用条件

Catalogへの登録は利用可能を意味しません。[Consumer Catalog](../../src/unityagent/runtime/reference_implementation/subagent-catalog.yaml) が要求するBackend availability、compatibility、Project binding、Artist Package、Pipeline reachabilityを現在のEnvironment Factで確認します。falseまたはunknownなら候補から除外し、Capabilityを満たすための自動Installは行いません。

<a id="setup-and-status-contract"></a>

## 診断・計画・適用の状態

Doctorは観測操作であり、製品をInstallしません。要求の `products` は観測対象を指定します。全体を必須化する `required` フラグはなく、任意製品が未導入でも観測自体は完了できます。

| 境界 | 状態の意味 |
|---|---|
| Installer Provider `status: passed` | 要求された観測を完了し、認識可能な製品状態を返した。全製品の導入成功ではない |
| Installer Provider `status: failed` | 観測実行または結果の形式が不正。対象項目の失敗理由を維持する |
| 製品 `status: verified` / `installed` | 対象製品の利用可能・導入状態を観測した |
| 製品 `status: unavailable` | 未検出・利用不可。`reason` と `message` を維持し、`verified` へ変更しない |
| 製品 `status: stale` | 観測したVersionが非互換。未検出や実行例外と区別する |
| Control Plane `status: completed` | 解決、Provider操作、Evidence処理が完了した |
| Control Plane `status: blocked` | 解決またはProvider操作を完了できなかった |
| CLI終了コード | `0` はControl Plane操作の完了、非0は失敗・阻害。個々の製品の利用可否を表す値ではない |

Setup WindowはControl Planeの構造化応答に従い、製品ごとの状態と解決・Providerの失敗理由を表示します。`UnityAgent: Ready` と `Artist CLI (backend): Unavailable` が同時に出ても、ArtistSubAgentが利用可能とは判断しません。利用可否のAuthorityはCapability解決です。

Doctor Evidenceは診断操作の状態を記録します。正規ハッシュには製品状態と利用不可理由を含むProvider結果が含まれます。Evidence化によって `unavailable` を `verified` に書き換えません。

Plan生成はInstallではありません。Applyには一致する承認済みPlanとApproval Referenceが必要です。要求していない任意製品をPlanの依存へ追加しません。独立した `project.inspect` 等は、それぞれの適格なProviderで解決します。実行例外は `failed` であり、製品の `unavailable` へ変換しません。

<a id="distribution-boundary"></a>

## 配布元とRevision

現在の同居定義は [Registry](../../subagent/registry.yaml) と参照先Manifestが入口です。Artist Backend PackageとHost Toolも `subagent/artist_subagent/tools/` に同居します。現行mainの [Release Workflow](../../.github/workflows/release-tag.yml) は同じUnityAgent checkoutから成果物を生成し、旧Hubを取得しません。

公開済み `v0.0.8-beta` は旧Hubの固定CommitからBackendを生成した過去の配布です。過去TagのWorkflowとProvenanceを、現在のmainの生成手順と混同しません。旧Hub Source LockとOffline Importは明示的な互換検証として維持します。

UnityAgentが公開ReleaseとMarketplaceの入口を所有し、ArtistSubAgentや旧Hubを独立した実行Authorityにしません。

<a id="codex-surface"></a>

## Codexの入口

公開Pluginの入口は `unity-agent` です。ArtistSubAgentは独立PluginとしてOrchestrationを迂回しません。Skillは委譲方法を説明しますが、Capability契約やAuthorityを別に定義しません。

<a id="compatibility"></a>

## 互換名

`unity_artist_cli`、実行ファイル `unity-artist`、既存Package名はBackend互換名として維持します。新しい説明で専門Agentの正本IDの代わりに使用しません。

<a id="offline-catalog-import-gate"></a>

## Offline Catalog Import

旧Hubのconsumer-neutral Snapshotは、明示的なOffline入力として既存Import Gateで検証できます。

```text
Snapshot + source_ref + expected SHA-256
    ↓
Identity / Capability / Provider / Activation / Evidence検証
    ↓
Added / Removed / Changed / No-opのImport Plan
```

`python tools/import_subagent_catalog.py` は読取専用です。取得、Project観測、Install、Catalog書込、Hot Reloadを行いません。`audience`、`goal_type`、`primary_capability`、Reference scope / approval、Evidence producer、既定ProfileはConsumer Catalogから保持します。これらの値がないSpecialistには明示的なCatalog Migrationが必要です。変更候補はGitでレビューし、保護Fieldの変更・削除はPlanで拒否します。

現行CatalogとReferenceImplementationの永続EvidenceのProducerは `UnityAgent.ReferenceImplementation.v1.1` です。neutral SnapshotはProducerを持ちません。旧Profile-wire形式は明示的な互換入力であり、Producer不一致は保護Field変更として扱います。`runtime_profile_revision` はProvider RegistryとSubAgent Catalogを含み、Resumeの実行中Action拒否とEvidenceのProfile binding digestを維持します。

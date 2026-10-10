# SubAgent Catalog Import Gate 運用

## 目的

Hubのconsumer-neutral SnapshotをUnityAgent所有の `SubAgentProfileCatalog` へOfflineで適合させ、反映前にレビュー可能なImport Planを作成します。Snapshotの読取成功はProviderのinstalled / compatible / project-bound / availableを意味しません。

## 実行

```bash
python tools/import_subagent_catalog.py \
  --snapshot /path/to/subagent-catalog.yaml \
  --source-ref 'github://DarumaPPAP/UnitySubAgentHub/<full-commit-sha>/Tests/Hub/export_agent_snapshot.py' \
  --expected-sha256 'sha256:<64 lowercase hex characters>'
```

`source-ref`とSHA-256は呼び出し側がSnapshotの取得元と取得バイト列に対して指定します。SHA-256が一致しない、YAMLに重複キーがある、Snapshot / Identity / Capability / Provider / activation / scope / approval / Evidenceが不正、または未知のEnvironment Factを参照するSnapshotはfail-closedになります。

Current Hub contractはSnapshot v3 / Manifest v5です。Import Gateは明示的な互換入力としてSnapshot v1 / Manifest v3とSnapshot v2 / Manifest v4も受け入れますが、旧版をCurrent契約へ暗黙変換しません。v3では`execution.kind`を含むExecution Contractを検証し、Provider-backed SpecialistはBackend宣言を要求し、Reasoning SpecialistはSemantic Tool Backendを持たないことを要求します。v3 Snapshotを取り込むConsumer CatalogはProfile v3でなければ`consumer_migration_required`で停止します。

AdapterはHub Schemaの固定コピーを`src/unityagent/runtime/reference_implementation/schemas/`からオフラインで検証し、active SpecialistのIdentity、Capability、Activation、Execution、Compatibility、Backend / Reasoning参照、Evidence requirementsを読みます。Hub Schemaが更新される場合はこのコピーとImport Testを同じUnityAgent PRで更新します。`audience`、`goal_type`、`primary_capability`、既定Profile、Reference scope / approval、Evidence producerなどConsumer所有値はUnityAgentの現行Catalogから保持します。HubがこれらのRuntime値を決めません。新しいSpecialistにUnityAgent側Profileがなければ`consumer_profile_required`で停止し、明示的なCatalog Migrationを要求します。複数のactive Specialistが同じCapabilityを宣言し、現行Consumerが一意に扱えない場合もImport Gateで拒否します。

## Development / Pinned互換性検証

Python 3.12+で、同じローカルHub Git Repositoryに対して両モードを独立して実行します。

```bash
python tools/validate_catalog_import_gate.py --hub-root /path/to/UnitySubAgentHub --source-mode development
python tools/validate_catalog_import_gate.py --hub-root /path/to/UnitySubAgentHub --source-mode pinned
```

DevelopmentはHubの`HEAD`、Pinnedは`src/unityagent/runtime/distribution/subagent-sources.lock.json`の完全なCommit SHAを使います。必要なCommitは事前にGitで取得してください。Validatorはnetwork fetchもcheckoutも行わず、各Commitを一時ディレクトリへ`git archive`で隔離展開し、そのCommitの既存Exporterを実行します。未Commit変更は検証対象に含まれません。Hub作業ツリー、Catalog、Source Lockは変更しません。固定Commitが取得できなければHEADへfallbackせず失敗します。

JSON Planには`source.mode`、`source.commit`、`source.locked_commit`、完全なCommitを含む`source.ref`、Snapshot SHA-256と既存Import Planを記録します。SHA-256はその実行で生成したバイト列の同一性を記録するもので、署名や事前に承認されたdigestとの照合ではありません。

CI互換性Gateは読取専用`no_op`だけを成功とし、`blocked`、`requires_pull_request`、不正入力、Export失敗は失敗とします。表示名変更など低リスク差分もレビューが必要です。正当な契約変更ではConsumer Profile / Schemaの明示Migrationをレビューし、両RepositoryのGateを再実行します。Source Lock更新は別途明示的に判断し、自動更新しません。

UnityAgent CIはHub mainのDevelopment HEADとPinned Sourceを検証し、それぞれのPlanをCI Evidence Artifactへ保存します。Hub CIは当該Hub Commitから生成したSnapshotをUnityAgent mainの既存Import CLIで検証します。相手Repositoryのmainは実行開始時に解決するため、横断契約変更のMerge後にも両Gateを再実行してください。これらのArtifactは検証記録であり、Hub ReleaseやRuntime同期を行いません。

## Planの扱い

出力Planには次が含まれます。

- `Added` / `Removed` / `Changed` / `No-op`
- 変更Field、protected Field、Risk
- Snapshotと現在Catalogの参照元およびSHA-256
- `catalog_write_performed: false` とPull Request要求

PlanをRuntimeへ直接Applyする経路はありません。変更が必要な場合は、現在のPolicyに従うGit差分と既存CIのレビュー対象にします。既存Run途中のHot Reloadは行いません。

## Producer差分と旧形式

現行UnityAgentのArtist Evidence producerは `UnityAgent.ReferenceImplementation.v1.1` です。consumer-neutral Hub SnapshotにはProducerを含めません。以前のProfile wire形式のSnapshotは既存の明示的な互換経路で読めますが、そこに異なるProducerがあれば`evidence.producer`のprotected-field変更としてブロックします。Producer契約を更新する場合はImporterとは別の契約変更PRで扱います。

## Runtime / Resume / Evidence

反映後も `unity_artist_cli.compatible` を含む必須Environment Factは、現在のProjectに対するUnityAgent Environment discoveryの三値観測で判定されます。false / unknown / unavailableは候補から除外されます。

CatalogとProvider Registryの変更は既存DefinitionFingerprintの `runtime_profile_revision` に含まれます。Resumeの既存Runtime Profile変更ルール、Reference Evidenceのprofile binding digestを緩和・追加拡張しません。

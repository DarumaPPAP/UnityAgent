# SubAgent Catalog Import Gate 運用

## 目的

Hubのconsumer-neutral SnapshotをUnityAgent所有の `SubAgentProfileCatalog` へOfflineで適合させ、反映前にレビュー可能なImport Planを作成します。Snapshotの読取成功はProviderのinstalled / compatible / project-bound / availableを意味しません。

## 実行

```bash
python Tools/import_subagent_catalog.py \
  --snapshot /path/to/subagent-catalog.yaml \
  --source-ref 'github://DarumaPPAP/UnitySubAgentHub/refs/heads/main/catalog.yaml' \
  --expected-sha256 'sha256:<64 lowercase hex characters>'
```

`source-ref`とSHA-256は呼び出し側がSnapshotの取得元と取得バイト列に対して指定します。SHA-256が一致しない、YAMLに重複キーがある、Snapshot / Identity / Capability / Provider / activation / scope / approval / Evidenceが不正、または未知のEnvironment Factを参照するSnapshotはfail-closedになります。

Hub Snapshot v1はManifest v3を含みます。AdapterはHub Schemaの固定コピーを`Runtime/ReferenceImplementation/Schemas/`からオフラインで検証し、active Specialistの静的Capability、Activation、Backend参照、Evidence requirementsを読みます。Hub Schemaが更新される場合はこのコピーとImport Testを同じUnityAgent PRで更新します。`audience`、`goal_type`、`primary_capability`、既定Profile、Reference scope / approval、Evidence producerはUnityAgentの現行Catalogから保持します。HubがこれらのRuntime値を決めません。新しいSpecialistにUnityAgent側Profileがなければ`consumer_profile_required`で停止し、明示的なCatalog Migrationを要求します。複数のactive Specialistが同じCapabilityを宣言した場合も、現行Resolverが一意に選べないためImport Gateで拒否します。

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

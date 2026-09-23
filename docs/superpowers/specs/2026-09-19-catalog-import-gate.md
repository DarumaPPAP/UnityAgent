# UnityAgent Catalog Import Gate 仕様

日付: 2026-09-19
状態: 実装対象の仕様（Task要求で承認済み）

## 目的

`UnitySubAgentHub/Tests/Hub/export_agent_snapshot.py` が生成する既存の
`SubAgentProfileCatalog` 形式のSnapshotを、UnityAgentの現在のCatalogへ自動反映せずに検証し、
差分と変更リスクをレビュー可能なImport Planとして出力する。

## 入力と境界

- 入力はOffline SnapshotのUTF-8バイト列とする。取得・Artifact download・Runtime観測は行わない。
- Snapshotは既存の `schema_version/default_profile/profiles` 形式をそのまま受け取る。汎用Catalog形式は追加しない。
- `source_ref` と期待SHA-256は呼び出し側が明示する。実バイト列のSHA-256と一致しない入力は拒否する。
- 現在のCatalogとRuntime Provider Registry、Environment Snapshot schemaはUnityAgent側の正本を読む。
- Import GateはCatalog、Provider、Project、Environment、Run、Resume、Evidenceを変更しない。

## 検証

Snapshot YAMLの重複キー・複数Document・UTF-8不正を拒否し、既存Profile parserによる厳密な型・必須Field・余分Field・Profile構造検証を通す。追加のSemantic Gateは次を検証する。

- `profile_id` / `provider_id` の形式と両者の分離、Catalog keyとの一致
- Provider Registryに存在し、production-disabledでないProvider
- Profile内およびCatalog全体のCapability、primary capability、goal type、provider idの一意性
- activationのoptional / `auto_install: false`、Environment Fact pathの正本schema存在
- scope、value、approvalの境界と型
- evidence provenanceの厳密な形

Environment Factの値は入力に含めず、Provider availabilityやProject bindingをImport成功とみなさない。Runtimeは反映後も現行Environment Snapshotで三値Eligibilityを判定する。

## Import Plan

各Profileについて `Added` / `Removed` / `Changed` / `No-op` を記録し、変更Field、保護Field、Risk、Snapshotの取得元とSHA-256、現在Catalogの参照とSHA-256、書込み未実施を構造化して出力する。

保護Fieldはidentity、routing（audience / goal / capabilities / primary）、activation、scope、value、approval、required evidence、evidence provenanceとする。保護Field変更・削除・default profile変更はPlanを `blocked` とし、変更を反映しない。その他の差分も `requires_pull_request` とし、Import Gateから直接Applyしない。

## Producer contract alignment

2026-09-23時点で、Hub ManifestとUnityAgent Runtime Catalogはともに現在のproducerを `UnityAgent.ReferenceImplementation.v1.1` としている。初期実装時に記録したHub Manifestとのproducer差分は解消済みであり、現行のSource of Truth競合ではない。

Import Gateは、将来入力されたSnapshotのproducerがConsumer側契約と異なる場合も自動補正しない。既存 `artist_subagent` の保護Field変更として拒否し、契約変更は両Repositoryでレビューする。

## Revision / Resume / Evidence

既存のDefinitionFingerprintの `runtime_profile_revision` に Provider RegistryとSubAgent Catalogの両方を含める。既存のResume rule（in-flight actionがあるRuntime Profile変更はblock）を利用し、Fingerprint schemaを拡張しない。Reference Evidenceは既存profile binding digestと同じCatalog変更追跡を保持する。

## 非対象

Catalogの自動Apply、Runtime Hot Reload、HubへのResolver/Installer/Environment discovery/Project binding、Provider ranking、GitHub Artifactの自動取得、Artist backend改造、既存Policyの緩和は行わない。

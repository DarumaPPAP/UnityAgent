# ArtistSubAgent

ArtistSubAgentはUnityのVisual Art、LookDev、Lighting、Environment、Camera、Cinematicを扱うOptional Specialistです。UnityAgentから委譲され、独立したControl Planeにはなりません。

## 識別子と担当範囲

| Concern | Value |
|---|---|
| Specialist ID | `artist_subagent` |
| Display name | `ArtistSubAgent` |
| Current backend ID | `unity_cli` |
| Backend executable | 公式Unity CLI `unity` |
| Backend Unity Package ID | `com.darumappap.artist-subagent` |

`artist_subagent`は専門Agent、`unity_cli`は実行BackendのIdentityです。独立Artist Hostは不要です。

## 静的契約

[Manifest](manifest.yaml)がIdentity、Lifecycle、Optional Installation、Activation、Compatibility、Dependencies、Backend参照、Evidence requirementsの正本です。現在のResolver-visible Capabilityは次の3件です。

- `artist.camera.inspect`
- `artist.camera.refine`
- `visual.capture`

Backend内部の全9コマンドは `inspect`、`plan`、`preview`、`apply`、`capture`、`evaluate`、`refine`、`history`、`cinematic` です。公式Unity CLIのPipelineへ登録し、既存の `uagent artist` EntryからControl Plane／Tool Brokerを通して実行します。同居定義は[Capability contract](contracts/capability-contracts.yaml)と[Backend interface](contracts/backend-surface-contract.yaml)を所有します。変更実行とCapture ReviewはControl Planeの承認をEditor側で実行直前に照合し、Project／Run／Plan／Revision／Exact Diff／Context／実変更先と承認Scopeを一致させます。

| Unity | Render Pipeline |
|---|---|
| Unity 6.x+ | Built-in |
| Unity 6.x+ | URP |
| Unity 6.x+ | HDRP |

Unity 2022.3は現行Production対象外です。過去の実測はHistorical Evidenceであり、現在のFallback Transportではありません。

## 利用条件とEvidence

ManifestはBackend availability、Compatibility、Project binding、Package installation、Pipeline reachabilityを必要なEnvironment factsとして宣言します。UnityAgentが現在値を観測し、falseまたはunknownを候補から除外します。Capability解決時の自動Installは行いません。SetupはUnityAgentの`doctor → setup plan → approval → setup apply → doctor`による明示的な別操作です。

ManifestはEvidence types、required artifacts、terminal statesのみを宣言します。[Release verification](https://github.com/DarumaPPAP/UnitySubAgentHub/blob/c5a593dfcaeea0f902999e91a97b620214db063f/ci/evidence/artist/historical/release-verification.yaml)はBackend側の検証記録であり、Hub Manifestの参照先ではありません。Runtime Evidence producer、正規化、永続化はUnityAgentの責務です。`blocked_by_environment`は成功ではありません。

## UnityAgentのImport境界

`subagent/registry.yaml` が同居Manifestを索引し、同居Exporterが静的Snapshotを生成します。UnityAgentは `src/unityagent/runtime/reference_implementation/subagent-catalog.yaml` をRuntime Catalogとして所有します。旧HubのSnapshotは明示的なOffline互換入力として検証し、登録やArtifact公開だけでRuntime Catalogを同期・Hot Reloadしません。

Artist UPMの正本は同じUnityAgent Repositoryの `subagent/artist_subagent/tools/editor/` です。Control Planeの型付きEntry、Unity CLI Provider、Installerは `src/unityagent/` にあります。独立Artist HostをBuild／Install／実行する経路は使用しません。現在の責務境界は[ArtistSubAgentの責務境界](../../docs/architecture/artist-subagent-boundary.md)を参照してください。

リンクした互換記録は履歴Evidenceです。現在のWorking TreeのImport／Compile／Editor／Mutation Security／全9コマンドE2E／配布Revisionは、それぞれ対応する新しい実行記録で判定します。未実行は `BLOCKED_NOT_RUN`、未観測は `not_observed` とし、静的な配布物検査だけで利用可能や統合完了と判断しません。

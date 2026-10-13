# ArtistSubAgent

ArtistSubAgentはUnityのVisual Art、LookDev、Lighting、Environment、Camera、Cinematicを扱うOptional Specialistです。UnityAgentから委譲され、独立したControl Planeにはなりません。

## Identity and domain

| Concern | Value |
|---|---|
| Specialist ID | `artist_subagent` |
| Display name | `ArtistSubAgent` |
| Current backend ID | `unity_artist_cli` |
| Backend executable | `unity-artist` |
| Backend Unity Package ID | `com.darumappap.artist-subagent` |

`unity_artist_cli`は実行BackendのIdentityであり、Specialist IDの代替ではありません。

## Static contract

[Manifest](manifest.yaml)がIdentity、Lifecycle、Optional Installation、Activation、Compatibility、Dependencies、Backend参照、Evidence requirementsの正本です。現在のResolver-visible Capabilityは次の3件です。

- `artist.camera.inspect`
- `artist.camera.refine`
- `visual.capture`

Backend内部のコマンド一覧はResolver-visible Capabilityを増やしません。Hubは[Capability contract](contracts/capability-contracts.yaml)と[Backend interface](contracts/backend-surface-contract.yaml)を所有します。コマンドと安全性のRelease確認は[Backend release contract](../../../cli/artist/artist-backend-contract.yaml)で行います。

| Unity | Render Pipeline |
|---|---|
| Unity 6.x+ | Built-in |
| Unity 6.x+ | URP |
| Unity 6.x+ | HDRP |

Unity 2022.3は現行Production対象外です。過去の実測はHistorical Evidenceであり、現在のFallback Transportではありません。

## Activation and evidence

ManifestはBackend availability、Compatibility、Project binding、Package installation、Pipeline reachabilityを必要なEnvironment factsとして宣言します。UnityAgentが現在値を観測し、falseまたはunknownを候補から除外します。Capability解決時の自動Installは行いません。SetupはUnityAgentの`doctor → setup plan → approval → setup apply → doctor`による明示的な別操作です。

ManifestはEvidence types、required artifacts、terminal statesのみを宣言します。[Release verification](../../../ci/evidence/artist/historical/release-verification.yaml)はBackend側の検証記録であり、Hub Manifestの参照先ではありません。Runtime Evidence producer、正規化、永続化はUnityAgentの責務です。`blocked_by_environment`は成功ではありません。

## UnityAgent import boundary

Hubは静的Snapshotを公開します。UnityAgentは`Runtime/ReferenceImplementation/subagent-catalog.yaml`を自分のRuntime Catalogとして所有し、Offline Import AdapterでSnapshotの差分を検証します。Hubの登録やArtifact公開だけでRuntime Catalogを同期・Hot Reloadしません。

Artist Package、CLI、Installer、Backend Tests、Releaseは現在同じRepository内のArtist Backend Productに属します。詳細は[Hub Architecture](../../../docs/architecture/subagent-hub-architecture.md)と[Ownership audit](../../../docs/architecture/authority-cleanup-audit.md)を参照してください。

Compatibility records linked here are preserved historical sessions. Current Unity Editor / Pipeline / visual validation is `BLOCKED_NOT_RUN` / `not_observed`; static archive checks do not establish activation readiness.

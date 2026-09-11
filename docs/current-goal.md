# Current Goal: UnityArtistCLI cutover

## Goal statement

既存Runtimeを再利用し、UnityAgentをArchitect / Commander / Loop Owner、UnityArtistCLIをvisual art / cinematic specialist Provider（概念上のPlayer）として運用する。Unity CLIはgeneric Unity操作の第一Provider、UnityArtistCLIはLookDev・Lighting・Environment・Camera・Cinematic・Timeline・Visual Evaluation / Refineを担当する。

## Canonical runtime

`CapabilityRequest -> Runtime Guard -> ToolBroker -> Resolver -> Environment Snapshot -> Provider Registry -> Dispatcher -> Provider Adapter -> ProviderResult -> Evidence Normalizer -> Persistence`

Artist要求は `domain.workflow` / `visual.capture` とsemantic qualifierで表現し、UnityAgent側に第二のPlayer FrameworkやRegistryを追加しない。旧 `myunitymcp` は履歴互換のため保持するが、legacy / production-disabledとする。

## Release matrix

- Unity 2022.3 LTS + Built-in
- Unity 6.x+ + Built-in
- Unity 6.x+ + URP
- Unity 6.x+ + HDRP

2022.3 Built-inもOfficial Unity CLI + Unity Pipelineを第一候補とし、年式だけで別Backendへ切り替えない。Matrix外のUnity 2022.3 URP/HDRP、Unity 2023、URP 14–16はMutation前にtyped failureを返す。

## Non-goals

- UnityAgent内の第二のPlayer Framework / Provider Registry
- UnityArtistCLIでのgeneric GameObject / hierarchy / compile / test / build / play操作
- UnityArtistCLIへのMCP transport、arbitrary eval、raw Unity YAML mutationの追加
- Unity 2023およびUnity 2022.3 URP/HDRPの正式サポート

## Completion

- UnityArtistCLIのCLI envelope、host transport、Artist package、compatibility bucket、support matrix、safe mutation lifecycleが実装されている
- UnityAgentのsemantic routing、`unity_artist_cli` Provider、Environment facts、legacy cutover、Evidence mappingが既存Runtimeへ接続されている
- UnityAgent / UnityArtistCLIのskill-only PluginとUnityAgent Marketplace manifestが検証可能である
- Static、host CLI、package contract、resolver、plugin、release matrix、E2E EvidenceをPASS / FAIL / BLOCKEDで監査する
- Unity Editor / License / Pipeline reachabilityなど未観測の条件は成功扱いせず、`blocked_by_environment` として記録する

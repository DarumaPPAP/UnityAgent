# PerformanceSubAgent Production 登録契約

`manifest.yaml` と `contracts/production-capability-contract.yaml` が現行の登録契約です。`contracts/capability-contracts.yaml` は登録前の候補評価を保存する履歴資料です。Capabilityは`performance.analyze`のみで、計測の実行、Provider選択、変更適用、Approval、RoutingはUnityAgentが管理します。

PerformanceSubAgentは観測済みのCPU / GPU / Memory / GC等のEvidenceを解釈し、bottleneckの分類、仮説、必要な追加観測、Recommendationを返します。ShaderやRenderGraphの実装正当性はGraphicsSubAgentの領域です。Profiler、ProfilerRecorder、FrameTimingManager等は決定論的なMeasurement Tool Surfaceであり、Specialist Identityではありません。

HubはIdentity、Capability、Read-only、Compatibility、Evidence、Receipt境界を定義します。UnityAgentのProduction Consumer ProfileがActivation、Context、Routeを定義します。必須観測の`profiler.observe`はUnity CLI / PipelineのEditor Snapshotを条件付きで取得し、`limited`として伝搬します。登録とProduction Verifiedは別であり、実Unity ProjectのEditor / Player / Target DeviceおよびLive A/B/Cは`NOT_EVALUATED_RUNTIME`です。

# Decision: UnityArtistCLI provider cutover

Date: 2026-09-10

## Decision

UnityAgentは新しいPlayer Frameworkを実装せず、既存の Capability → Provider Registry → Resolver → Dispatcher → Provider Adapter → Evidence chainへ `unity_artist_cli` を追加する。UnityAgentはArchitect / Commander / Loop Owner、UnityArtistCLIはvisual art / cinematicを実行するspecialist Provider（概念上のPlayer）とする。

## Reasons

- Artist系は `domain.workflow` と `visual.capture` のsemantic qualifierで選択でき、Provider製品名をOrchestrationへ漏らさない。
- Unity CLIのgeneric操作とUnityArtistCLIのArtist操作を分離できる。
- 旧 `myunitymcp` は `legacy: true` / `production_enabled: false` として履歴とv1.1.1タグを保持しつつ、現行経路の選択から除外できる。
- 2022.3 Built-inはOfficial Unity CLI + Unity Pipelineを第一候補として実測し、PipelineのUnity 6以上要求を具体的なGate Failureとして記録できる。

## Rejected alternatives

- UnityAgent内に別のPlayer Manager / Registryを追加することは、既存Runtimeと二重化するため採用しない。
- 2022.3という理由だけで別Backendへ切り替えることは、正式仕様に反するため採用しない。
- `unity-cli-loop` の動的コード実行経路をArtistのFallbackに使うことは、arbitrary eval禁止と競合するため採用しない。
- UnityArtistCLIへGameObject / hierarchy / compile / build / play / stop / logなどのgeneric Unity操作を戻すことは、責務重複になるため採用しない。

## Evidence

- Official `unity` CLI 1.0.0-beta.8で `2022.3.22f1` のEditor識別に成功。
- `unity pipeline install` は `2022.3.22f1` に対して「Pipeline packageにはUnity 6.0以降が必要」とexit 1。fallback成功扱いなし。
- Registry、qualifier resolver、provider adapter、CLI contract、plugin schemaの静的／ホストテストは実行可能。
- Unity Editor接続、Pipeline reachability、Timeline実機Mutation、四Matrixの全実機E2Eは、現環境では未観測またはblocked_by_environment。

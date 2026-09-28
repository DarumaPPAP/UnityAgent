# Specialist Context Assembly — 監査と実装範囲

## 2026-09-25 の監査

| 領域 | 既存の正本 | 今回の差分 |
| --- | --- | --- |
| Task Route | `Orchestration/Routing/task-routes.yaml` | Artist の既存２ Route に Specialist identity と必須 Policy 参照を宣言 |
| Specialist identity / eligibility | `Runtime/ReferenceImplementation/subagent-catalog.yaml` と `profiles.py` | Orchestration が既存 Catalog を参照し、未導入・不適合・不明を選外にする |
| Context 選別 | `Context/Selection/` と `Context/Packs/` | Task tag に一致する型付き項目だけを選択 |
| Context 生成 | `Context/Assembly/materialize_context.py` | 同じ MaterializedContextView と Context Manifest に Specialist 内容を追加 |
| Budget / 出典 | `Context/Budget/context-budget.yaml`、Context Fingerprint | 専門情報の実際の UTF-8 byte 数と Revision を算入 |
| Provider 実行 | `Runtime/Tooling/tool_broker.py` | **変更なし**。CapabilityRequest と Policy / Approval を既存 Runtime が処理 |
| Hub | `UnitySubAgentHub/Registry/`、`SubAgents/artist_subagent/manifest.yaml` | **変更なし**。Project／Platform の現在値を Manifest へ保存しない |

現在の Artist Profile が公開するのは `artist.camera.inspect`、`artist.camera.refine`、`visual.capture` のみ。Artist Backend に Texture Importer 最適化の公開コマンドはない。したがって Texture Optimization は今回の実行 Pilot にできず、未実装の Capability を追加して成功に見せることもしない。既存の `visual.capture` を Host 側の経路検証に使う。

## Contract と流れ

`resolve_specialist(route_id, capability, environment_snapshot)` は Orchestration に属し、`status` と `profile_id` を返す。Provider ID は返さない。`selected` の場合だけ、同じ `materialize_context` が `specialist_selection`、`specialist_items`、`specialist_tags`、`required_specialist_keys`、必要なら `specialist_skill_ref` を受け取る。`build_context_manifest.build` も同じ引数を転送する。

Candidate SpecialistはProduction Catalogと別の `Runtime/ReferenceImplementation/candidate-specialists.yaml` から参照する。Routeの `specialist_profile` は専門的な意味解析のOwnerを示し、ApplyやProvider解決のOwnerではない。`specialist_phase: analysis` の候補は `entry_action: implement` のRouteでも診断・事前確認・提案Diffまでを担当する。Taskの変更要求とSpecialist Capability自身の変更権限を区別する。ActivationはProject存在、読み取り可能性、対応Unity Versionを判定し、Capability ContextはRender Pipelineや対象Source等の観測事実を別途要求する。欠落Factは `required_context_missing` として停止し、推測しない。

WorldCreator Candidateは`execution_mode: planning_only`、`provider_resolution: not_required`、`receipt_required: false`を組合せで検証し、`world-creation` Routeの`specialist_phase: planning`へ束縛する。`world.plan`はStructured World Plan Artifactを返し、UnityAgentが後続のRoute、Policy、Approval、Capabilityを再解決する。Work Packageの`domain_hint`はRoute決定ではない。Providerless CandidateにProvider、ProviderResult、Generated→Transported→Received Receiptを作らず、Plan Artifactの`source_context_id`と`source_context_fingerprint`を生成元Manifestに照合する。Pilotの静的fixtureはPlanning reasoningのProduction実行を証明しない。

WorldCreatorのPlanning reasoningは、`Runtime/Contracts/runtime-handoff.schema.yaml`の`specialist_reasoning`から既存CodexRunnerへ渡す。`generic_planning`、明示的な`--sandbox read-only`、隔離Workspace、`--output-schema`、原Projectの変更観測、JSON Schemaと`verify_world_plan`の意味検証を組み合わせる。Context Manifestの`context_id`とfingerprintをHandoff、Runner入力、Plan Artifactで照合する。ProviderlessはToolBroker Providerが不要という意味であり、Model Runtimeの不存在を意味しない。Production instructionは`.agents/skills/world-planning/SKILL.md`であり、Eval DatasetのinstructionをRuntimeへ投入しない。
CodexRunnerのReasoning実行は`--ignore-user-config`を指定する。CLI 0.150.1のhelpではこのflagはユーザー設定を読み込まず、認証には既存のCodex homeを使う。HostがModelとReasoning Effortを渡すため、ユーザー設定のModel選択や追加Tool設定をExecution Authorityにしない。Live Smokeでも認証とStructured Outputの成立を確認した。Model revisionがHostから観測されない場合は`not_observed`として記録する。
Planning-onlyを有効にしたRunではPersistence rootを元Unity Projectの外へ置く。Control PlaneはProject内のPersistenceを実行前に拒否し、CodexRunnerの隔離Workspaceと出力は一時領域を使う。これによりOriginal Projectの変更観測にUnityAgent自身のRuntime Artifact書込みを混ぜず、変更Pathが1件でもあれば失敗とする。

WorldCreatorのProduction Registry登録は引き続き`BLOCKED_BY_ARCHITECTURE`である。Hub Manifest v4はBackendを1件以上要求し、Production `SubAgentProfile`とCatalog Import GateはProvider bindingを要求する。Reasoning Runtime経路の実装はこれらのSchemaを変更しない。Provider-backedとReasoning-onlyをProduction登録契約で表すには、Manifest、Profile、Import Gateの次版を別途設計する。今回のControlled Runner fixtureは実Unity Editor/Player/Device検証ではない。

Specialist CapabilityはEntry Intentの分岐で決めない。OrchestrationのRouteが生成するProduction CapabilityRequestとCandidate用の意味的CapabilityRequestを集め、Routeに束縛されたProfileのCapability集合と交差させる。一致が0件または複数件なら停止する。Candidate用の要求はProduction dispatchへ渡さず、Provider Registryへの架空Graphics Provider登録も行わない。`goal_type` とHubの旧 `primary_capability` は実行時選択に使わない。

Specialist 項目の型は `project_fact`、`project_decision`、`platform_fact`、`platform_decision`、`task_fact`。それぞれ key、value、tag、source、SHA-256 revision、freshness を保持する。Fact は観測 attempt を指定する。Decision は `user:` または `project_policy:` に由来する明示的な判断に限定する。unknown／stale／別 attempt の情報は採用しない。必須情報が無ければ生成を停止し、Budget 超過でも必須情報を捨てない。全項目を一つの選択済み Specialist bundle として測定し、その全 byte 数と出典を記録する。

既存 Route の primary Skill は維持する。追加 Skill は Orchestration から対象に適した `.agents/skills/<name>/SKILL.md` を明示したときだけ全文を選択し、全 Skill を常時読み込まない。Policy は Route の必須参照を全量含める。Context は Specialist を選出せず、Runtime の Provider を決めない。

`specialist_context` は既存 MaterializedContextView 内の optional section である。Context Fingerprint は Specialist 項目の revision と内容を反映する。Runtime Handoff は既存 `context_id` と `context_fingerprint` を受け取れる。第二の Context Engine、Control Plane、Provider Registry は作らない。実行時の承認、Scope、Evidence、Completion Gate は従来の経路が担当する。

Production の `UnityAgentControlPlane.execute` は v2 Entry を検証し、既存 EnvironmentSnapshot の Project binding と ProjectVersion.txt を照合し、`ProjectFactObservation` と Specialist 項目を組み立てる。Orchestration の `select_route` が Task Fingerprint から Primary Route を選び、既存 `build_capability_requests` が provider-independent CapabilityRequest を生成する。Specialist はこの生成済み Capability から選出する。既存 Context Manifest に渡し、保存した `within_budget` の Context ID / Fingerprint を Runtime Handoff に渡す。必須 binding や Budget が不足する場合は Provider dispatch より前に停止する。v1 Entry 契約は書き換えず、caller 指定の Context Identity を持つ v1 実行を明示的に migration required として拒否する。v2 は Context Identity と Route / CapabilityRequest を受け取らない。

Control Plane は既存 Persistence の immutable snapshot に Task Fingerprint、Route Decision、active conditions、Task Contract projection、生成 CapabilityRequest、Context Manifest ref を保存する。これにより Handoff の各値が Orchestration 由来であることを Host で照合できる。

### Entry → Orchestration Authority

| 値 | 正本と生成元 |
| --- | --- |
| Project / Task 意図、承認参照 | Entry の明示 request。ただし Project access は EnvironmentSnapshot の bound 状態と Policy の許可でのみ current とする |
| Task Fingerprint | Orchestration が Typed Intent から決定的に投影し、Project access は EnvironmentSnapshot と Policy から生成。未知・欠落・未許可は停止 |
| Primary Route / Execution Profile | `Orchestration/Routing/route_selector.py::select_route`。Entry の `route_id` / `execution_profile` は受理しない |
| Active conditions / CapabilityRequest | `Orchestration/ToolRouting/capability_request_builder.py` と既存 capability-routing catalog。Entry の `capability_requests` は受理しない |
| Node ID | 既存 ParentGraph の Runtime action node (`inspect_sources` / `execute_change`) を Orchestration が選ぶ |
| Task Contract Runtime projection / validation requirements | Route に対応する既存 Task Contract の risk / task-level quality gates を projection に保持する。Runtime validation requirements は生成 CapabilityRequest の required evidence に限定する。Capability 実行の完了を Task Contract 全体の完了と混同しない |
| Mutation Scope | read-only Pilot は空の scope を Orchestration が生成する。Entry の `mutation_scope` は受理しない。Mutation は既存の Project scope / Approval / source byte 観測を結ぶ projection が揃うまで dispatch 前に停止 |
| Context ID / Fingerprint | UnityAgent Context Assembly のみ。Entry から受理しない |

v2 Entryの `project_inspection` / `visual_capture` に加え、登録済みReasoning Profileの `rendering_diagnosis` / `world_planning` を共通Control Planeで処理する。GraphicsはTool観測後にCapability Contextを最終判定し、WorldCreatorは既存planning Runtimeを使用する。Production実行経路はRepository fixtureで検証し、Live Provider / Unity Evidenceとは区別する。Entry の７次元 Fingerprint は受理しない。`project_inspection` の事前 evidence は `unknown`、`visual_capture` は過去の障害 evidence を要求しないため `not_applicable` と投影する。未対応Mutation実行、未知または不完全な Typed Intent、要求 Outcome に合う Capability がない Route は dispatch 前に停止する。Camera FOV reference の既存 v1.1 専用 projection は一般の Artist Task Contract から生成できないため、旧 live runner の v2 移行は未完了であり、preflight / apply より前に明示停止する。専用 projection を Entry の任意値として再導入して通したことにはしない。

`artist-lookdev` が以前必須としていた Hub の外部 spec は、現在の Runtime が参照する同一 repository の canonical `subagent-catalog.yaml` に置き換えた。Hub を複製せず、外部取得の未観測値を恒久的に current 扱いしない。Local source は revision ごとに一度だけ Budget に算入し、複数の意味上の参照は `selected_refs` に保持する。

## Pilot / Baseline 比較

下表は変更前の Host fixture の記録であり、現行 Production の比較結果ではない。`utf8-bytes-conservative-v1` の推定であり、モデル Token 数の実測ではない。

| 項目 | Baseline | Candidate |
| --- | ---: | ---: |
| 選択 artifact 数 | 10 | 13 |
| 選択 byte 数 | 45,474 | 48,911 |
| 推定 token 数 | 15,158 | 16,304 |
| Budget 判定 | unmeasured | unmeasured |

Candidate には Project Fact、Project Decision、Platform Fact、Platform Decision、Task Fact の５項目を投入。別 Project Decision／Platform Fact で Fingerprint が変わり、Audio 情報は Camera Task へ混入しない。Artist 不可時に Specialist のみ unavailable とし、既存 `project.inspect` は File Provider に解決される。`visual.capture` は既存 CapabilityRequest と ToolBroker を通して `artist_subagent` / `unity_artist_cli` に解決された。

現行の Production 経路を模擬 Provider と実際の一時 Unity Project 構成で実行した Artist capture fixture では、14 artifact、47,125 bytes、推定 15,709 tokens、`within_budget` となった。ただし Unity Editor は起動していない。この数字は実 Editor Task の成功証拠ではない。Task success、Editor／Pipeline 到達、実 Provider Evidence は未観測。`unmeasured` / `blocked` のまま mutation は許可しない。

3-way 比較器は `Eval/Regression/compare_specialist_three_way.py`。A: Specialist なし、B: 候補を選別しない Naive、C: Filtered の fixture で artifact／bytes／推定 tokens、不要 source、Contract Task success、Evidence completeness、Tool calls／Retries、必須 Context と受信 Identity 一致を判定する。Host fixture の合格は LLM reasoning 品質や実 Unity Editor 成功を証明しない。実 run の測定値を記録していない場合、実測結果としては報告しない。

## Context receipt の境界

- Generated: Context Assembly が immutable Manifest に `context_id` と `context_fingerprint` を生成する。
- Transported: ToolBrokerがProviderを解決した後、Runtime Dispatcherが対応可能な解決済みProviderへ共通の `specialist_execution_context` とManifest pathを渡す。ContextとSpecialist identityはProviderを選ばない。非対応Providerでは実行前に停止する。
- Received: Backendがstructured resultに `received_context_id` / `received_context_fingerprint` を返す。Receipt必須のSpecialist CapabilityではRuntime Dispatcherが生成Identityと照合し、欠落・不一致をfail-closedとする。通常CapabilityにはReceiptを要求しない。
- Applied: Specialist inference / decision input への実適用は今回未評価。受信 Echo を semantic consumption と呼ばない。

現行 Production の正式対象は Unity 6.x+（Built-in / URP / HDRP）。Unity CLI は automation / command surface、Unity Pipeline は実行中 Editor の local HTTP bridge であり、connected Editor commands に使う。Unity 2022.3 は現行 Support 対象外。Historical bounded batch Evidence は別途保存する。Skill は既存 `.agents/skills` / Context catalog の metadata から選別し、必要な SKILL.md と Reference のみ段階的にロードする。Hub の `skill_refs` 追加は現時点で必須ではない。

Hub Generic Artist Manifest / Export Snapshot v2 は Camera FOV Reference 固有の scope、value、approval を含まない。UnityAgent の現行 ReferenceImplementation Catalog v1 は既存 Camera FOV の歴史的契約として保持する。Offline Import Gate は Hub v2 Snapshot を構文・意味検証した後、保護フィールド差分を `blocked` として明示的 migration を要求する。v1 Catalog を無言で v2 の汎用 Profile に置換しない。

## Reasoningの必須観測とContext binding

Production reasoning Profileの `execution.required_observation_capabilities` は、意味的Capabilityを実行する前に必要なTool観測を表す。Control Planeは既存CapabilityRequest / ToolBroker経路で観測を実行する。読取結果の構造化payloadは、実行ログ・Provider搬送metadataを除外し、既存の機密値redactionを適用してimmutable snapshotへ保存する。payloadのdigestと参照をExecutionEvidenceに結び付け、Persistence append後にのみ再利用する。

Reasoning前にEvidenceStoreがRun、Project、Capability、durability、verification、必須Evidence、event chain、payload digestを照合する。Control Planeは実行時のdefinition fingerprintも照合する。必須Capabilityごとに対応するdurable Evidenceが一意でない場合、未観測・部分検証・改変済みの場合はReasoningを開始しない。read以外の操作結果は、この読取観測契約へ暗黙変換しない。

検証済み観測はContext Selectionの `project_fact:observation:<capability>` に投影する。Tool出力は未信頼の観測データであり、PolicyやInstructionではない。既存Context Assemblyで全量をBudgetへ算入し、Context fingerprintを再生成する。Budget超過は停止し、観測を黙って削って通さない。新Manifestを参照するHandoffとOrchestration Decisionを生成し、旧Manifest参照と観測Evidence IDを残す。Reasoning Artifactはこの更新後のContext ID / fingerprintへ束縛する。

`test_reasoning_runtime_handoff.py` は実ToolBroker、EvidenceStore、Context Assembly、Handoffとcontrolled Codex processを通し、観測内容の到達・Fingerprint更新・Evidence欠落時の停止・Budget超過を検証する。これはRepository fixtureであり、Live Reasoningや実Unity Runtimeの成功証拠ではない。Production Catalogへの各Specialist登録は別のPromotion Gateで判定する。

## 登録済みReasoningのActivationとContext Gate

Graphics / WorldCreatorはConsumer Catalog v3のReasoning Profileとして登録する。HubのManifest v5 / Snapshot v3との一致は固定fixture `hub-production-specialists-v3.yaml` をImport Gateへ通して検証する。PerformanceのInstructions / Output Contractは用意するが、Production観測Surface `profiler.observe` の不足を理由に未登録とする。登録そのものはProduction Verifiedを意味しない。

観測を必須とするReasoning Profileでは、Orchestrationは最初に `activated` を返す。この状態はVersionとEnvironmentの適格性だけを示し、Specialist Contextの生成やReasoning実行を許可しない。最初のHandoffは `capability_dispatch` である。必須観測を永続検証した後、既知の観測フィールドをFactへ投影して再選出する。`project.inspect.render_pipeline` と `source.read.path/content` が対象であり、任意のProvider出力をTask Decisionへ変換しない。unknown PipelineはFactとして採用せず、`required_context_missing` で停止する。

最終選出が `selected` となり、再構築ManifestのBudgetとBindingが成立した場合だけ、共通 `specialist_reasoning` Handoffを生成する。Providerless RuntimeへObservation Capabilityを意味的Capabilityとして送らない。失敗理由、観測Evidence、旧Manifest参照を保持する。

Renderingの初期分析では明示症状と対象Scopeを必須とする。`verification_requested` / `mutation_requested` の段階では再現条件、正確なError、対象Source、RendererFeature順序を追加必須とする。Context Packの条件付き項目に `required_when_active: true` があれば、当該条件の選択時に欠落をGate failureとする。初期分析の完了は再現検証やApplyの完了ではなく、従来のTask ContractのCompile / Runtime / Mutation Gateを満たしたと主張しない。

`test_graphics_production_reasoning.py` は本番Catalog・ToolBroker・FileProviderによるProject設定観測とSource読取・EvidenceStore・Context・Handoffを使用し、Projectのファイル内容とCodex processをfixture化する。適格Contextでの到達、unknownでの停止、Read-only維持、再現段階の不足Contextを検証する。FileProviderはProjectVersion・GraphicsSettings・QualitySettingsを実ファイルから読取り、Built-in / URP / HDRPの一意な構成だけを採用する。Quality別の不一致、未解決GUID、独自Pipeline、設定欠落はunknownとし、観測範囲をserialized_project_configurationと記録する。実Editorのactive quality、Scriptによる実行時切替、Live Reasoning、Player/実機の品質は別途検証が必要である。Host CLIの `run --request` はEntry v2を既存Control Planeへ渡し、FileProviderが解決された場合だけ観測を実行する。明示対象Sourceがない場合、別Fileを推測して読まない。

## CI / Host 完了条件と未評価事項

Host / CI では、read-only Pilot の Authority、生成 Context、Budget、Backend 受信 Identity、Artist unavailable 時の Core Capability、A/B/C fixture 比較を検証する。Unity Editor / CLI / Pipeline の live 接続と Specialist の判断品質は Required Gate ではなく `not_evaluated` と報告する。Texture Pilot は別 Work／別 PR とする。

専門領域の品質低下には Evidence → Fact freshness → Context selection → Skill → Tool／Provider → Specialist instruction → Domain ownership の順に原因を確認する。Platform、Pipeline、Asset 種別だけを理由に SubAgent を増やさない。

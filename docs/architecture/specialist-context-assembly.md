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

v2 Production の実行対象は `project_inspection` / `visual_capture` の read-only outcome。Entry Schemaには `rendering_diagnosis` を追加し、そのRepository fixtureはRoute、候補選出、Context、静的Evidenceまで検証する。Production Control PlaneのGraphics実行経路とLive Provider Evidenceは未評価。Entry の７次元 Fingerprint は受理しない。`project_inspection` の事前 evidence は `unknown`、`visual_capture` は過去の障害 evidence を要求しないため `not_applicable` と投影する。未対応Mutation実行、未知または不完全な Typed Intent、要求 Outcome に合う Capability がない Route は dispatch 前に停止する。Camera FOV reference の既存 v1.1 専用 projection は一般の Artist Task Contract から生成できないため、旧 live runner の v2 移行は未完了であり、preflight / apply より前に明示停止する。専用 projection を Entry の任意値として再導入して通したことにはしない。

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

## CI / Host 完了条件と未評価事項

Host / CI では、read-only Pilot の Authority、生成 Context、Budget、Backend 受信 Identity、Artist unavailable 時の Core Capability、A/B/C fixture 比較を検証する。Unity Editor / CLI / Pipeline の live 接続と Specialist の判断品質は Required Gate ではなく `not_evaluated` と報告する。Texture Pilot は別 Work／別 PR とする。

専門領域の品質低下には Evidence → Fact freshness → Context selection → Skill → Tool／Provider → Specialist instruction → Domain ownership の順に原因を確認する。Platform、Pipeline、Asset 種別だけを理由に SubAgent を増やさない。

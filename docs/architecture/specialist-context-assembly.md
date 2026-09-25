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

Specialist 項目の型は `project_fact`、`project_decision`、`platform_fact`、`platform_decision`、`task_fact`。それぞれ key、value、tag、source、SHA-256 revision、freshness を保持する。Fact は観測 attempt を指定する。Decision は `user:` または `project_policy:` に由来する明示的な判断に限定する。unknown／stale／別 attempt の情報は採用しない。必須情報が無ければ生成を停止し、Budget 超過でも必須情報を捨てない。全項目を一つの選択済み Specialist bundle として測定し、その全 byte 数と出典を記録する。

既存 Route の primary Skill は維持する。追加 Skill は Orchestration から対象に適した `.agents/skills/<name>/SKILL.md` を明示したときだけ全文を選択し、全 Skill を常時読み込まない。Policy は Route の必須参照を全量含める。Context は Specialist を選出せず、Runtime の Provider を決めない。

`specialist_context` は既存 MaterializedContextView 内の optional section である。Context Fingerprint は Specialist 項目の revision と内容を反映する。Runtime Handoff は既存 `context_id` と `context_fingerprint` を受け取れる。第二の Context Engine、Control Plane、Provider Registry は作らない。実行時の承認、Scope、Evidence、Completion Gate は従来の経路が担当する。

Production の `UnityAgentControlPlane.execute` は v2 Entry を検証し、既存 EnvironmentSnapshot の Project binding と ProjectVersion.txt を照合し、`ProjectFactObservation` と Specialist 項目を組み立てる。既存 Orchestration の選出結果を同じ Context Manifest に渡し、保存した `within_budget` の Context ID / Fingerprint を Runtime Handoff に渡す。必須 binding や Budget が不足する場合は Provider dispatch より前に停止する。v1 Entry 契約は書き換えず、caller 指定の Context Identity を持つ v1 実行を明示的に migration required として拒否する。v2 は Context Identity を受け取らない。既存 Camera FOV live runner も v2 と Artist の canonical route に移行した。

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

3-way 比較の記録器は `Eval/Regression/compare_specialist_three_way.py`。A: Specialist なし、B: 候補を選別しない Naive、C: Filtered の３つの実 run について Context Manifest、Runtime result、durable Evidence を入力し、選択 artifact／bytes／推定 tokens、不要な source、Task success、Evidence completeness、Tool calls／Retries を計算する。全 arm の実 run と関連 source 一覧が揃うまで比較合格とはしない。現環境に Unity Editor executable がないため比較の実測は未完了。

## 実運用へ進める条件

1. Editor のある実 Unity Project で、v2 Entry から Unity CLI／Pipeline／Editor まで既存 `visual.capture` を実行し、durable Evidence を検証する。
2. 同じ Task で A / B / C を記録し、C が B より小さい Context で同等以上の Task success / Evidence completeness を達成したことを判定する。
3. Texture Pilot は別 Work／別 PR で Capability、Approval、Evidence、Backend surface を設計する。

専門領域の品質低下には Evidence → Fact freshness → Context selection → Skill → Tool／Provider → Specialist instruction → Domain ownership の順に原因を確認する。Platform、Pipeline、Asset 種別だけを理由に SubAgent を増やさない。

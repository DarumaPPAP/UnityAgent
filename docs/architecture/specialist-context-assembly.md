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

**接続上の未完了:** Production の `UnityAgentControlPlane.execute` は Entry が渡した `context_id` と `context_fingerprint` を使用しており、まだ `resolve_specialist` / `build_context_manifest.build` を呼び出さない。したがって本差分の選別は API / Host fixture で検証済みだが、Entry → Specialist Context → 実 Provider execution の自動接続は実装済みと主張しない。Entry が持つ Context と観測の責務を確定し、既存 Control Plane で照合する作業が必要である。

## Pilot / Baseline 比較

Host fixture で同じ `artist-lookdev` Route を比較した値。`utf8-bytes-conservative-v1` の推定であり、モデル Token 数の実測ではない。

| 項目 | Baseline | Candidate |
| --- | ---: | ---: |
| 選択 artifact 数 | 10 | 13 |
| 選択 byte 数 | 45,474 | 48,911 |
| 推定 token 数 | 15,158 | 16,304 |
| Budget 判定 | unmeasured | unmeasured |

Candidate には Project Fact、Project Decision、Platform Fact、Platform Decision、Task Fact の５項目を投入。別 Project Decision／Platform Fact で Fingerprint が変わり、Audio 情報は Camera Task へ混入しない。Artist 不可時に Specialist のみ unavailable とし、既存 `project.inspect` は File Provider に解決される。`visual.capture` は既存 CapabilityRequest と ToolBroker を通して `artist_subagent` / `unity_artist_cli` に解決された。

これらは **Host の決定的 fixture による経路・契約の確認**。Task success、first-pass success、Compile／Editor／Player 成功、視覚品質、Tool call／Retry 数、実行時間、実 Project での Context 圧縮率は未観測。必須 binding、外部 Hub reference、capability selection が未観測なので Budget は `within_budget` ではない。`unmeasured` の間は mutation を許可しない。

## 実運用へ進める条件

1. 対象 Project の Fact を取得し、各 source revision と attempt freshness を記録する。Project の明示 Decision は Fact と分離する。
2. 必須 binding、Hub 外部参照、Capability 選択を実測し、Context Budget を `within_budget` にする。
3. Control Plane の Entry 経路から Orchestration decision と Context Manifest を結び、Fingerprint を照合する。Budget `unmeasured` / `blocked` では実行を停止する。
4. 実 Unity Project で Before／After の Task success、初回成功、Evidence 完全性、誤った Project／Platform 推奨、選択 byte 数、Tool calls、Retries を比較する。
5. Texture Pilot を実行する場合、まず Backend の対応、Approval／Evidence 契約、Resolver 公開範囲を別途設計・実装・検証する。現状では Texture の **計画** 以外に実行可能と宣言しない。

専門領域の品質低下には Evidence → Fact freshness → Context selection → Skill → Tool／Provider → Specialist instruction → Domain ownership の順に原因を確認する。Platform、Pipeline、Asset 種別だけを理由に SubAgent を増やさない。

# 専門SubAgentを利用する

SubAgentは対応Taskの専門担当です。入口はUnityAgentのControl Planeで、直接Providerや専門Agentを呼び出してPolicy・承認を迂回しません。

## 担当と権限

以下はDevelopment Commit `95ec7214697c9c4690ea72a4949a0c90fd928a9b` の同居定義です。

| 正本ID・担当 | 公開Capability | 現在の権限と前提 |
|---|---|---|
| `artist_subagent` / ArtistSubAgent | `artist.camera.inspect`、`artist.camera.refine`、`visual.capture` | Provider-backed。Backendの導入・互換性・Project binding・Package・Pipelineが必要。変更は限定Scopeと承認付き |
| `graphics_subagent` / GraphicsSubAgent | `graphics.inspect`、`graphics.diagnose`、`graphics.validate` | 読取専用分析。Project・読取権限とTaskに対応するFact・観測を要求 |
| `world_creator_subagent` / WorldCreatorSubAgent | `world.plan` | 計画のみ。World Goalと要求Scopeが必要。Human Reviewを要求し、Unityへの直接変更を行わない |
| `qa_subagent` / QASubAgent | `performance.analyze` | 読取専用分析。性能症状・要求Scope・対象環境と検証済み観測Receiptが必要。観測の取得はUnityAgentが管理 |

Artist Backendの内部コマンド数を、Specialistが公開するCapability数に読み替えません。Graphics・WorldCreator・QAはCodexRunnerの推論引き継ぎを使用し、Tool Providerを偽装しません。

公開 `v0.0.8-beta` ではQAへの改名前のPerformanceSubAgentが登録されています。現在の `qa_subagent` と、旧 `performance_subagent` の明示的な入力互換を区別してください。実装上の正式IDを一括置換する操作は不要です。

## 自動選出と明示指定

通常は依頼の意図と対象からOrchestrationがRouteを選び、Consumer Catalogの必要条件を満たす担当を解決します。登録だけで選出・導入・実行は成立しません。

Entry v2の任意項目 `requested_subagent` は担当希望を明示するためのものです。Routeの担当と一致し、導入・互換性・Binding・環境・Context Gateを満たす場合だけ利用されます。未導入の担当を強制実行したり、必要条件を省略したりする指定ではありません。CLIに新しいSubAgent専用フラグや独立実行経路は追加しません。

## 利用前の確認

1. [最初の操作](../getting-started/first-task.md) でProjectと開発環境を確認する。
2. 対象Taskの必要条件を [Consumer Catalog](../../src/unityagent/runtime/reference_implementation/subagent-catalog.yaml) と対応Manifestで確認する。
3. 未導入・未Bind・非互換・環境不明なら、必要な導入を別のSetup Planとして確認・承認する。Capability解決に伴う自動Installは行わない。
4. 変更を伴う場合は対象・Revision・Scope・承認を確認し、実行後のEvidenceとGateを読む。

Doctorの製品状態とSpecialistの適格性は別の境界です。QAの `profiler.observe` は条件付きのEditor Snapshotで、`limited` を維持します。Player・実機の連続計測やGPU timingを推測で補完しません。

## 正本と検証状態

同居Manifestの入口は [Registry](../../subagent/registry.yaml) です。RuntimeのActivation・ContextはConsumer Catalog、選出は [Task Route](../../src/unityagent/orchestration/routing/task-routes.yaml) が管理します。

登録、Fixtureの存在、Host契約検査、実モデル推論、実Unity・Player・実機での検証は別です。[機能の状態表](../references/capability-status.md#専門subagent) で対象RevisionとGateを確認してください。詳しい境界は [Specialist Context Assembly](../architecture/specialist-context-assembly.md) にあります。

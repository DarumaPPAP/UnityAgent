---
name: unity-production-workflow
description: Use when a Unity request contains multiple phases, uncertain routing, implementation plus verification, or a request to autonomously progress toward a production-ready result. Owns the Supervisor state machine, execution contract, specialist routing, recovery decisions, evidence review, and human handoff. Does not duplicate specialist implementation, incident, rendering, shader, or measurement procedures.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  version: "2.0.0"
---

# Unity Production Workflow

Unity案件の入口となるSupervisor Skill。
依頼を一本道の工程へ押し込まず、Goal、Constraints、Observability、Recoveryを保持した状態遷移として管理する。
専門作業は対応Skillへ委譲し、このSkill自身は順序、Gate、遷移、停止、人間への引き渡しを所有する。

共通モデルは`SkillReferences/UNITY_AGENT_SUPERVISOR_MODEL.md`を参照する。

## Delegates to

必要なものだけを読む。全Skillを一括で読み込まない。

- `unity-specify` — 検証可能なGoal、非目標、受け入れ条件
- `unity-plan` — 責務、依存、所有権、Migration、Rollback
- `unity-tasks` — 安定Task ID、変更境界、Done条件
- `unity-implement` — 選択TaskまたはConfirmed Fixの最小差分
- `unity-review` — 仕様、互換性、差分、証拠の受入Gate
- `unity-incident-investigation` — コンパイル、実行時、描画、Editor / Player差の原因調査
- `csharp-antipattern-audit` / `csharp-safe-patch` — C#の監査と確定Findingの修正
- `unity-rendering` — URP、RenderGraph、RendererFeature、Shader固有境界
- `shader-performance-auditor` / `shader-performance-refactor` — Shader監査と確定Findingの修正
- `unity-shader-variant-governor` — Keyword、Variant、Strip、Strict Variant
- `unity-runtime-evidence` / `shader-runtime-evidence` — Before / After実測
- `production-code-comments` / `learning-code-comments` — 完成コードへの日本語コメント

## Step 1 — Build the execution contract

依頼文、利用可能なファイル、Project Profileから次を確定する。

### Goal

コード生成ではなく、成立させる最終状態を書く。

### Constraints

- 変更対象と変更禁止範囲
- Unity、Render Pipeline、Platform、Editor / Player、Mono / IL2CPP
- public API、SerializeField、Prefab / Scene、Save Data
- Shader Property、Keyword、Pass、LightMode、RenderState
- ユーザーが明示した禁止事項と停止条件

### Observability

Goalごとに成功と失敗を判定できる観測方法を割り当てる。

1. Static inspection
2. Local validator / unit test
3. Unity compilation / Console
4. Editor reproduction / screenshot
5. Player / IL2CPP
6. Target-device measurement

観測手段が存在しない条件は、未検証事項として扱う。

### Recovery

Compile、Runtime、Visual、Performance、Scope、Contract conflictごとに戻り先と停止条件を定義する。
失敗理由に関係なく単純に実装へ戻さない。

既存ファイルから確定できる内容を質問し直さない。
破壊的変更、対象Platform、保存互換性など、誤ると作業全体が無効になる情報だけを停止条件にする。

## Step 2 — Determine the current state

開始時と各観測後に、現在Stateを一つ選ぶ。

- `INTAKE`
- `CONTEXT_REQUIRED`
- `READY`
- `PLANNING`
- `INVESTIGATING`
- `IMPLEMENTING`
- `STATIC_VALIDATION`
- `UNITY_VALIDATION`
- `DOMAIN_VALIDATION`
- `VISUAL_OR_RUNTIME_VALIDATION`
- `EVIDENCE_REVIEW`
- `AWAITING_HUMAN_DECISION`
- `AWAITING_HUMAN_APPROVAL`
- `REVERT_REQUIRED`
- `ACCEPTED`
- `BLOCKED`

状態の意味と遷移条件は`SkillReferences/UNITY_AGENT_SUPERVISOR_MODEL.md`を正本とする。

## Step 3 — Select exactly one primary lane

### Lane A — Explanation / read-only analysis

使用条件:

- 「何をしているか」「原因を説明して」「設計を評価して」
- コード変更を求められていない

処理:

- Stateは通常`READY`からRead-only専門Skillへ委譲する。
- 事実、推論、未確認事項を分離する。
- 実装案を出しても勝手にファイル変更しない。

### Lane B — Incident / regression

使用条件:

- コンパイルエラー、例外、表示崩れ、Editor / Player差、回帰
- 原因が未確定

処理:

- `INVESTIGATING`へ遷移し、`unity-incident-investigation`をPrimaryにする。
- C#、Rendering、Shader、Variantの専門Skillは証拠に応じて一つずつ追加する。
- 原因未確定のまま複数箇所を同時変更しない。

### Lane C — Feature / behavior change

使用条件:

- 新機能、既存仕様変更、複数ファイルの設計変更

処理:

1. Execution Contractを作る。
2. 複数責務、Migration、互換性変更があれば`PLANNING`へ遷移する。
3. 必要な規模だけ`unity-specify -> unity-plan -> unity-tasks`を使う。
4. 選択Taskだけを`IMPLEMENTING`で処理する。
5. 指定Taskが`ACCEPTED`になっても次Taskへ自動遷移しない。

単一ファイルの局所修正で、要件、変更範囲、受け入れ条件が明確なら、形式的なSpec一式を増やさない。

### Lane D — Performance optimization

使用条件:

- CPU、GC、GPU、Overdraw、Variant、RenderGraph、メモリ、ロード時間

処理:

1. 指標、再現Scene、Platform、品質設定、計測区間をObservabilityへ固定する。
2. Read-only監査を先に行う。
3. 主要仮説を一つに限定する。
4. 最小変更を実装する。
5. Runtime EvidenceでBefore / Afterを比較する。
6. `EVIDENCE_REVIEW`でAdopt / Rework / Revert / Inconclusiveを判定する。

未計測なら改善を断定しない。

### Lane E — Review / acceptance gate

使用条件:

- コードレビュー、仕様審査、PRレビュー、完成判定

処理:

- `EVIDENCE_REVIEW`として`unity-review`へ委譲する。
- FindingをCorrectness / Compatibility / Performance / Maintainabilityに分類する。
- CriticalまたはErrorが残る場合は`AWAITING_HUMAN_APPROVAL`へ進めない。
- 必要な実機証拠がなければEvidence RequiredまたはInconclusiveにする。

## Step 4 — Expose only the required tools

現在StateとPrimary Skillに必要なToolだけを使用する。

- 調査中にWrite / Editを先行しない。
- Planning中にUnity実行Toolを無意味に要求しない。
- C#修正AgentへShader、Scene、Build管理Toolを一括公開しない。
- Visual検証が必要なときだけPlay / Screenshotを使う。
- Target-device Toolがない場合は実機検証済みと推測しない。

巨大な万能MCPまたは全Tool一括公開を前提にしない。

## Step 5 — Execute one bounded action

一回のMutationで扱う対象は次のいずれか一つに限定する。

- 選択Task
- Confirmed Finding
- 主要仮説

- 仕様外のController、Manager、Fallback、Cache、Debug UI、追加Passを作らない。
- public / serialized / Shader契約を変更する場合は、依頼またはSpecに根拠を持つ。
- 別問題を発見しても現在Patchへ混ぜず、Findingまたは別Taskとして分離する。

## Step 6 — Validate and route by failure class

### Static failure

命名、Namespace、Editor / Runtime境界、依存、差分、互換性、禁止事項を確認する。
失敗した場合は対象差分だけを`IMPLEMENTING`へ戻す。Scope violationなら`REVERT_REQUIRED`も検討する。

### Unity failure

Compile、Console、EditMode、PlayModeを確認する。
原因未確定なら`INVESTIGATING`へ戻し、エラーを隠す修正をしない。

### Domain failure

Rendering、Shader、Variant、AOT、Burst / Jobsなどの専門Skillへ委譲する。
Domain外の大規模変更へ逃げない。

### Visual or runtime failure

スクリーンショット、Player、実機、ProfilerをGoalと比較する。
Visual failureとPerformance failureを同じ修正ループへ混ぜない。

### Evidence review failure

- Goal未達 -> `IMPLEMENTING`または`INVESTIGATING`
- 証拠不足 -> `CONTEXT_REQUIRED`
- 回帰または安全条件違反 -> `REVERT_REQUIRED`
- 仕様判断が必要 -> `AWAITING_HUMAN_DECISION`

## Step 7 — Human handoff

次はAgentだけで最終決定しない。

- 公開API、Serialization、Save Dataの破壊的変更
- Renderer / Shader Pipelineの設計変更
- 品質と性能のトレードオフ
- 外部Package追加
- ファイル削除または大規模Scene / Prefab変更
- 実機品質の最終承認
- PR Merge

判断材料、差分、証拠、代替案、Revert条件を提出する。

## Output contract

最終報告には次を含める。

- Goalと達成状態
- 最終State
- Primary lane / Primary Skill
- Task IDまたはIncident ID
- 変更ファイル
- 主要仮説または変更理由
- 保持した互換性契約
- 実施した検証階層
- 観測結果と証拠
- 実行したRecovery
- 未検証事項
- Revert条件
- 人間判断が必要な項目

## Scope — what this Skill does not do

- 専門Skillの手順をコピーしない。
- 依頼されていない新システムを設計しない。
- 小さな修正へ巨大なSpec一式を強制しない。
- 原因調査、機能追加、最適化を同じPatchへ混ぜない。
- Editor成功だけでPlayerまたはConsole実機を保証しない。
- ユーザーが指定していない次Taskへ進まない。
- 人間の承認が必要な契約を勝手に変更しない。

## Checklist

- [ ] Goalをコード生成以外の成立状態として定義した
- [ ] Constraintsを固定した
- [ ] 各GoalへObservabilityを割り当てた
- [ ] Failure classごとのRecoveryを定義した
- [ ] 現在Stateを一つ選んだ
- [ ] Primary laneとPrimary Skillを一つにした
- [ ] 必要なToolだけを使用した
- [ ] Mutationを一つのTask、Finding、仮説へ限定した
- [ ] 失敗原因に応じた状態へ戻した
- [ ] 未検証事項とRevert条件を残した
- [ ] 人間承認が必要な項目を分離した

## Common mistakes

- 依頼を固定フローへ押し込み、失敗しても同じ場所へ戻す。
- コードまたはファイルを生成した時点で完了扱いする。
- 全Skill、全Reference、全Toolを毎回読み込む。
- Compile Error、Visual mismatch、Performance regressionを同じ修正として扱う。
- 原因未確定のIncidentで複数Subsystemを同時変更する。
- 指定Task完了後に次Taskへ自動で進む。
- 実行していないUnityコンパイルや実機検証を完了扱いする。

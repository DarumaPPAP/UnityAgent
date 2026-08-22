# UnityAgent Context Engineering

## Goal

UnityAgentの専門知識を失わず、Taskごとに必要なSkill、Reference、Sourceだけを読み込む。

## Selection flow

```text
Execution Mode
  ↓
.ai/context-index.yaml
  ↓
One Primary Route
  ↓
One Context Pack
  ↓
Typed Required + satisfied Typed Conditional references
  ↓
Target Source and direct dependencies
```

## Typed Context Pack v3

Context Packの`required`と`conditional`は、文字列ではなく型付きMappingで記述する。

### `binding`

Task実行時に解決される値またはSource Binding。

```yaml
- type: binding
  name: target_source
```

### `repository_reference`

UnityAgent Repository内の実在Artifactを読む。

```yaml
- type: repository_reference
  path: SkillReferences/CODING_STANDARDS.md
```

### `external_reference`

別RepositoryのArtifactを参照する。`DarumaPPAP/MyUnityMCP/Specs/...`のような文字列をUnityAgent内ローカルパスとして扱わない。

```yaml
- type: external_reference
  repository: DarumaPPAP/MyUnityMCP
  path: Specs/UnityAgentMCP/spec.md
```

### `context_include`

現在のPrimary Routeを維持したまま、別Context Packを追加Contextとして選択する。

```yaml
- type: context_include
  context_id: shader-change
```

IncludeされたContextを暗黙に再帰展開しない。Expansion Hopは1を上限とする。

### `route_handoff`

現在のTask責務を別Primary Routeへ移す必要があることを表す。

```yaml
- type: route_handoff
  route_id: rendering-incident
```

`context_include`と`route_handoff`を同義に扱わない。前者はContext追加、後者はPrimary Ownershipの変更である。

## Required / Conditional / Excluded

Context Packは資料を三種類へ分ける。

### Required

Task成立に必須。Binding、Repository Reference、External Reference等を型付きで宣言する。

### Conditional

Variant変更、RenderGraph、Burst、Visual、Runtime Measurementなど、条件が成立した場合だけ読む。

### Excluded by default

Taskと無関係なSupervisor、Visual、C# Catalog、Shader Catalogなど。必要性がEvidenceで判明した場合だけ別RouteまたはSecondary Skillとして追加する。

## Project Fact precedence

`Specs/ProjectProfile.md`はRequired Contextではなく、必要なProject Factが未解決の場合だけ使用するFallbackとする。

Project Factは次の順で解決する。

1. 対象Unity Projectから直接検出した事実
2. 今回ユーザーが確認したProject Fact
3. Project固有Context
4. `Specs/ProjectProfile.md`によるFallback

検出済みFactとProject Profileが競合した場合、Project Profileで上書きしない。Project Profileを読む場合は、どの未解決Factを補うために必要だったかを記録する。

Context PackではProject Profileを`required`へ置かず、使用する場合は`conditional.project_fallback`の`repository_reference`へ限定する。

## Project Fact provenance and freshness

Project Factは値だけを保存しない。最低限、次を記録する。

```yaml
key: unity.version
value: 6000.3.0f1
source_kind: detected_project
source_path: ProjectSettings/ProjectVersion.txt
revision: sha256:...
observed_at_attempt: 1
freshness:
  status: current
  checked_at_attempt: 2
reason: project_fact
```

`source_kind`は`detected_project`、`user_confirmed`、`project_profile`のいずれかとする。

`freshness.status`は次の意味を持つ。

- `current`: 現Attemptで再確認済み
- `stale`: 過去の観測値であり、現在値として使用しない
- `unknown`: 現在性を確認できない

`current`を名乗るFactは、`freshness.checked_at_attempt`が現在のManifest Attemptと一致しなければならない。

Retryでは前AttemptのProject Factを暗黙コピーしない。同じ`revision`を継続利用する場合でも、現在値として扱うなら現Attemptで再検証し、`checked_at_attempt`を更新する。

`observed_at_attempt`は最初に観測したAttemptを保持してよい。つまり「いつ発見したか」と「最後に現在性を確認したか」を分離する。

## Primary Skill

各StateまたはPrompt TaskでPrimary Domain Skillは一つにする。Secondary SkillはPrimaryが所有しない専門判断だけを補う。

例:

- RenderGraph errorの原因未確定: IncidentがPrimary、RenderingがSecondary
- Shaderの確定済み修正: RenderingまたはShader RefactorがPrimary
- 美的Scene設計: Visual DirectionがPrimary、RenderingがSecondary

## Context expansion

Contextを追加するAgentは次を記録する。

- 追加するArtifact
- 追加が必要な判断
- 現在のEvidenceでは不足する理由
- Expansion Hop

「念のため」で全Referenceを読み込まない。

`context_include`を使う場合も、Include先のConditional Contextを自動的に全展開しない。

## Knowledge Graph

Knowledge Graphは候補Artifactを選ぶNavigation Layerである。

```text
Query -> Candidate artifacts -> Direct source read -> Decision
```

禁止:

- Graphだけで原因を確定する
- 推論Edgeだけで互換性を判断する
- Graph Report全文を毎回Contextへ入れる
- Unity生成Folderを無制限にIndexする

Pilot契約は`.ai/knowledge-graph-pilot.yaml`を参照する。

## Measurement

最低限次を記録する。

- 選択Route
- Context Pack
- Typed Context種別
- Project Fact revision / freshness
- Initial file reads
- Expanded files and reason
- Retrieved context tokens
- Direct source tokens
- Missed dependency
- Verifier verdict

## Quality gate

Context削減は品質低下を正当化しない。

- 重要Dependency漏れが増えた場合はPackを修正する。
- Verifier Approvalが低下した場合は採用範囲を戻す。
- Token削減だけで成功判定しない。
- stale/unknown Factをcurrentとして扱う変更はRejectする。
- `context_include`と`route_handoff`を混同する変更はRejectする。

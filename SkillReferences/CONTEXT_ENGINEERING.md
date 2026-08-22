# UnityAgent Context Engineering

## Goal

UnityAgentの専門知識を失わず、Taskごとに必要なSkill、Reference、Sourceだけを読み込み、必要十分なContext量へ制御する。

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
  ↓
.ai/context-budget.yaml
  ├─ Retrieval measurement
  ├─ Context estimate
  └─ Compression / stop decision
  ↓
Budgeted Context Manifest
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

## Context Budget

Context選択量のCanonical Contractは`.ai/context-budget.yaml`とする。

Context BudgetはModel BillingやLoop全体のCost Budgetではない。UnityAgentが**一回のDomain Attemptへ渡すRetrieved Context量**だけを管理する。

### Retrieval Budget

実測できる次の値を使う。

- Artifact数
- Original UTF-8 bytes
- Selected UTF-8 bytes
- External fetch数
- Context Include数
- Expansion Hop

UnityAgent Repository内Sourceは実ファイルから自動計測できる。

Project SourceとExternal Repository Sourceは、次のObservationを必要とする。

```yaml
retrieval_observations:
  - source_id: project:Assets/Example.cs
    role: target_source
    source_revision: sha256:...
    original_utf8_bytes: 12000
    selected_utf8_bytes: 6200
    compression:
      mode: lossless_excerpt
      selected_ranges:
        - L1-L140
```

Observationが無いProject / External Sourceを「0 byte」として扱わない。未計測は`unmeasured`とする。

### Context estimated tokens

Provider Tokenizerへ依存しないBudget判定では、UTF-8 byteから保守的な推定値を作る。

```text
estimated_tokens = ceil(selected_utf8_bytes / 3)
```

これは**正確なModel Token数ではない**。

- `estimated_tokens`と明記する。
- Billing TokenやProvider Tokenと同一視しない。
- 正確なTokenizerで計測できた場合は追加Evidenceとして記録してよい。
- Provider Tokenizer名が無い値を`exact_tokens`と呼ばない。

英数字だけでなく日本語Contextでも大幅な過小評価を避けるため、Phase 3初期値は保守的なbyte基準とする。

## Budget profiles

Routeごとに`tight / standard / wide`のBudget Profileを選ぶ。

- `tight`: 局所C# Fixなど、小さいContextで成立するTask
- `standard`: Shader、Renderer Feature、Asset、Portable Feature等
- `wide`: Rendering IncidentやGraphics MCPなど、複数Evidenceが必要なTask

Profile閾値は`.ai/context-budget.yaml`が正本であり、現時点では`provisional_thresholds: true`である。

閾値を厳しくする場合はGolden Regressionと実測を先に確認する。Context品質を落として閾値だけ達成しない。

## Context Compression

CompressionはCanonical Sourceを書き換える処理ではない。**今回Modelへ渡す選択Contextだけを縮める処理**である。

### Compression mode

#### `none`

全文を選択する。`original_utf8_bytes == selected_utf8_bytes`でなければならない。

#### `lossless_excerpt`

Source本文を要約せず、必要Rangeだけを選択する。

- Source Revision必須
- Selected Range必須
- Target Source / Direct Dependency / Required Contextに使用可能
- 省略部分を存在しなかったことにしない

#### `semantic_summary`

意味を保持した要約Contextを使う。

使用可能範囲を限定する。

- Knowledge
- Background Reference
- Previous Failure summary

`summary_revision`を必須とし、どの要約結果をBudget計測したか追跡する。

### Lossy Compression禁止対象

次は全文保持を基本とし、Semantic Summaryしない。

- User Policy
- Context Pack
- Primary Skill
- Task Contract
- Project Fact

Authoritative ContractをBudget都合で要約し、Ruleを欠落させることを禁止する。

### Target Source

Target SourceやDirect DependencyはSemantic Summaryしない。

必要ならSource Revisionを保持した`lossless_excerpt`を使用する。Mutation対象の元Sourceへ追跡できない圧縮結果を実装根拠にしない。

## Budget decision

Budget Reportは次のいずれかになる。

### `within_budget`

必要Artifactが計測済みでSoft Limit以下。Mutationを開始できる。

### `compression_required`

Hard Limit以内だがSoft Limit超過。候補Contextを圧縮して再計測する。

### `unmeasured`

Project / External Sourceなど必要Observationが不足している。Budget PASSではない。

### `blocked`

Hard Limit、Artifact数、External Fetch数、Expansion Hop等を超えている。

Required Contextを黙って削除してPASSへ変えない。Context選択自体を見直すか、責務をHandoffする。

Mutation Taskでは`within_budget`以外を実行許可にしない。

## Compression order

Contextが大きい場合は次の順で削減する。

1. 同一Revision Sourceの重複を除去
2. 成立していないConditional Contextを除去
3. Relevant RangeだけLossless Excerpt
4. Non-authoritative Knowledge / BackgroundをSemantic Summary
5. 不明なBindingはContext追加で推測せずUnresolvedのまま残す
6. Hard Limitを満たせなければ停止

「先に重要Ruleを要約して削る」順番にしない。

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
- Retrieved artifact count
- Original / Selected UTF-8 bytes
- Estimated Context Tokens
- Exact Provider Token count when tokenizer evidence is available
- Compression mode / saved bytes
- Missing retrieval observations
- Budget decision
- Missed dependency
- Verifier verdict

## Quality gate

Context削減は品質低下を正当化しない。

- 重要Dependency漏れが増えた場合はPackを修正する。
- Verifier Approvalが低下した場合は採用範囲を戻す。
- Token削減だけで成功判定しない。
- stale/unknown Factをcurrentとして扱う変更はRejectする。
- `context_include`と`route_handoff`を混同する変更はRejectする。
- `estimated_tokens`を正確なModel Token数として報告する変更はRejectする。
- Authoritative ContextへのLossy CompressionをRejectする。
- Mutationを`compression_required / unmeasured / blocked`のまま開始する変更はRejectする。

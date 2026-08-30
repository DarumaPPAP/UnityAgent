# UnityAgent Context Engineering

## Goal

UnityAgentの専門知識を失わず、Taskごとに必要なPolicy、Skill、Reference、Sourceだけを選択し、必要十分なContext量へ制御する。

Contextは**current-call materialization**を所有し、Route selection、durable State、Memory、Checkpoint、Evidence truthを所有しない。

## Canonical selection flow

```text
User Request
  ↓
Task Fingerprint
  ↓
Orchestration/Routing/task-routes.yaml
  ↓
One Primary Route
  ↓
Context/Selection/context-catalog.yaml
  ↓
One Context Pack
+ One Primary Skill
+ One canonical Task Contract
+ Required Policy Clauses
+ satisfied Conditional Context
  ↓
Target Source and direct dependencies
  ↓
Context/Budget/context-budget.yaml
  ├─ Retrieval measurement
  ├─ Context estimate
  └─ Compression / stop decision
  ↓
Context/Assembly/materialize_context.py
  ↓
MaterializedContextView
```

Technology keywordだけでRouteを決めない。Context catalogはRouteを選ばず、Orchestrationが選択済みのRouteをmaterializeする。

## Typed Context Pack v3

Context Packの`required`と`conditional`は型付きMappingで記述する。

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

別RepositoryのArtifactを参照する。外部Repository pathをUnityAgent内ローカルpathとして扱わない。

```yaml
- type: external_reference
  repository: DarumaPPAP/MyUnityMCP
  path: Specs/UnityAgentMCP/spec.md
```

### `context_include`

現在のPrimary Routeを維持したまま、追加Context Packを選択する。

```yaml
- type: context_include
  context_id: shader-change
```

Include先を無制限に再帰展開しない。Expansion Hopはcontract上限を守る。

### `route_handoff`

現在Taskのsemantic ownershipを別Primary Routeへ移す必要があることを表す。

```yaml
- type: route_handoff
  route_id: rendering-incident
```

`context_include`と`route_handoff`を同義に扱わない。

## Required / Conditional / Excluded

### Required

Task成立に必須。Binding、Repository Reference、External Reference等を型付きで宣言する。

### Conditional

RenderGraph、Burst、Visual、Runtime Measurement、Project fallback等、条件成立時だけ読む。

### Excluded by default

Taskと無関係なDomain Skill、Catalog、Knowledge、Project Source等。必要性がEvidenceで判明した場合だけbounded expansionする。

全Skill、全Reference、全Knowledgeを一括読込しない。

## Project Fact precedence

`Specs/ProjectProfile.md`はRequired Contextではなく、必要なProject Factが未解決の場合だけ使用するFallbackとする。

Project Factは次の順で解決する。

1. 対象Unity Projectから直接検出した事実
2. 今回ユーザーが確認したProject Fact
3. Project固有Context
4. `Specs/ProjectProfile.md`によるFallback

検出済みFactとProject Profileが競合した場合、Project Profileで上書きしない。Profileを読む場合は、どの未解決Factを補ったか記録する。

Context PackでProject Profileを使用する場合は、`conditional.project_fallback`等の明示Conditionalとして扱う。

## Project Fact provenance and freshness

Project Factは値だけでなくprovenanceとfreshnessを記録する。

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

`source_kind`は少なくとも`detected_project`、`user_confirmed`、`project_profile`を区別する。

- `current`: 現Attemptで再確認済み
- `stale`: 過去値でありcurrentとして使用しない
- `unknown`: 現在性を確認できない

Retryで前AttemptのProject Factをcurrentとして暗黙コピーしない。

## Context Budget

Canonical Contract:

`Context/Budget/context-budget.yaml`

Context BudgetはModel BillingやLoop全体のCost Budgetではない。**一回のcurrent-callへ渡すretrieved Context量**を管理する。

Runtimeのexecution cost / hard execution limitsとは別責務である。

### Retrieval Budget

実測可能な主な値:

- Artifact数
- Original UTF-8 bytes
- Selected UTF-8 bytes
- External fetch数
- Context Include数
- Expansion Hop

UnityAgent Repository内Sourceは実ファイルから計測できる。Project SourceとExternal Repository Sourceは明示Observationを要求する。

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

Observationが無いSourceを`0 byte`として扱わない。未計測は`unmeasured`とする。

### Estimated tokens

Provider Tokenizerへ依存しないbudget判定では、現contractの保守的推定を使う。

```text
estimated_tokens = ceil(selected_utf8_bytes / 3)
```

これは正確なModel Token数ではない。

- `estimated_tokens`と明記する
- Billing Token / Provider Tokenと同一視しない
- 正確なTokenizer計測がある場合だけ追加Evidenceとして記録する

## Budget profiles

Routeごとに`tight / standard / wide`を使用する。現在の閾値とRoute mappingの正本は `Context/Budget/context-budget.yaml` であり、`provisional_thresholds: true` の間はGolden regressionとProduction measurementなしに閾値だけを厳しくしない。

## Context Compression

CompressionはCanonical Sourceを書き換えず、今回Modelへ渡す選択Contextだけを縮める。

### `none`

全文を選択する。

### `lossless_excerpt`

Source本文を要約せず必要Rangeだけを選択する。Source RevisionとSelected Rangeを保持する。

### `semantic_summary`

意味を保持した要約Context。Knowledge、Background Reference、Prior Failure等のnon-authoritative contextに限定する。

### Lossy Compression禁止対象

原則Semantic Summaryしない:

- User Policy
- Context Pack
- Primary Skill
- Task Contract
- Project Fact

Target SourceやDirect DependencyもSemantic Summaryせず、必要ならSource Revision付き`lossless_excerpt`を使用する。

## Budget decision

- `within_budget`: 必要Artifactが計測済みでsoft limit以下
- `compression_required`: hard limit内だがsoft limit超過
- `unmeasured`: 必要Observation不足。PASSではない
- `blocked`: hard limit等を超過

Required Contextを黙って削除してPASSにしない。

Mutation Taskはcurrent contractの`mutation_requires_within_budget`に従う。read-only analysisは`unmeasured`を報告できるが、budget PASSとは主張しない。

## Compression order

1. 同一Revision Sourceの重複を除去
2. 成立していないConditional Contextを除去
3. Relevant RangeだけLossless Excerpt
4. Non-authoritative Knowledge / BackgroundをSemantic Summary
5. 不明Bindingは推測せずUnresolvedのまま残す
6. Hard Limitを満たせなければ停止

Authoritative Ruleを先に要約して削らない。

## Primary Skill

Primary Domain Skillは一つにする。Secondary SkillはPrimaryが所有しない専門判断だけを補う。

例:

- RenderGraph errorの原因未確定: IncidentがPrimary、Renderingが必要時Secondary
- 確定済みC#局所修正: `csharp-safe-patch`
- 美的Scene設計: Visual DirectionがPrimary、Renderingは技術境界で補助

## Context expansion

Context追加時は次を記録する。

- 追加Artifact
- 追加が必要な判断
- 現Evidenceでは不足する理由
- Expansion Hop

「念のため」で全Referenceを読み込まない。

## Knowledge Graph

Knowledge Graphは候補Artifactを絞るNavigation Layerである。

Current pilot contract:

`Context/Retrieval/Knowledge/knowledge-graph-pilot.yaml`

```text
Query -> Candidate artifacts -> Direct source read -> Decision
```

禁止:

- Graphだけで原因確定
- 推論Edgeだけで互換性判断
- Graph Report全文を毎回Contextへ投入
- Unity生成Folderを無制限Index

## Measurement

最低限、必要に応じて次を記録する。

- selected Route
- Context Pack
- Typed Context種別
- Project Fact revision / freshness
- Initial / expanded readsと理由
- Retrieved artifact count
- Original / Selected UTF-8 bytes
- Estimated Context Tokens
- Exact Provider Token count when supported by tokenizer evidence
- Compression mode / saved bytes
- Missing retrieval observations
- Budget decision
- Missed dependency
- Verifier verdict

## Quality gate

Context削減は品質低下を正当化しない。

- 重要Dependency漏れが増えた場合はPackを修正する
- Verifier品質が低下したら選択範囲を戻す
- Token削減だけで成功判定しない
- stale/unknown Factをcurrentとして扱わない
- `context_include`と`route_handoff`を混同しない
- `estimated_tokens`を正確なModel Token数として報告しない
- Authoritative ContextへLossy Compressionしない
- Mutationを`compression_required / unmeasured / blocked`のまま開始しない

## Authority boundary

Contextはmaterialization layerである。

- Route / Graph decision -> `Orchestration/`
- current-call Context -> `Context/`
- process/tool execution -> `Runtime/`
- durable Memory / Checkpoint / Evidence -> `Persistence/`
- quality measurement -> `Eval/`

Legacy `.ai` pathやcompatibility fallbackをcurrent Context authorityとして使用しない。

# Unity Skill Routing

Unity依頼をどのSkillへ渡すかを決めるためのルーティング表。
迷った場合は`unity-production-workflow`を入口にし、Primary Skillを一つ選ぶ。

## Primary routing table

| User intent / observed state | Primary Skill | Secondary Skill | Do not start with |
|---|---|---|---|
| Unityの新機能を作りたい。要件が未整理 | `unity-specify` | `unity-production-workflow` | `unity-implement` |
| Specはある。構造と依存関係を決めたい | `unity-plan` | `unity-rendering`など対象専門Skill | `unity-implement` |
| Planを実行単位へ分解したい | `unity-tasks` | なし | `unity-implement` |
| Task IDが指定され、コード変更を求められた | `unity-implement` | 対象専門Skill | `unity-specify` |
| 原因不明のコンパイルエラー、例外、回帰 | `unity-incident-investigation` | C#またはRendering監査 | 大規模リファクタリング |
| Unity C#を変更せず監査したい | `csharp-antipattern-audit` | `unity-runtime-evidence` | `csharp-safe-patch` |
| 確定したC# Findingを最小修正したい | `csharp-safe-patch` | `unity-review` | 新規設計 |
| URP / RenderGraph / RendererFeatureを設計・実装 | `unity-rendering` | `unity-plan`または`unity-implement` | 汎用C# Skillだけ |
| Shader/HLSLの負荷・危険箇所を監査 | `shader-performance-auditor` | `shader-runtime-evidence` | `shader-performance-refactor` |
| 確定したShader Findingを修正 | `shader-performance-refactor` | `unity-review` | 未計測の全面最適化 |
| Keyword、Variant、Strip、Strict Variant | `unity-shader-variant-governor` | `shader-runtime-evidence` | Shaderコードの無関係な変更 |
| C#変更のCPU/GC/Player/実機Before/After | `unity-runtime-evidence` | `unity-review` | 静的推測だけの承認 |
| Shader/GPU変更のBefore/After | `shader-runtime-evidence` | `unity-review` | ソース行数だけの判定 |
| 完成した変更を受入レビュー | `unity-review` | 対象Audit/Evidence Skill | 新規機能追加 |
| 本番コードへ最小限の日本語コメント | `production-code-comments` | `comment-quality-reviewer` | `learning-code-comments` |
| 学習用に詳しい日本語コメント | `learning-code-comments` | `comment-quality-reviewer` | `production-code-comments` |
| 複数工程が混在し、入口が不明 | `unity-production-workflow` | 選択されたPrimary Skill | 全Skill一括読込 |

## Intent classifiers

### 「作りたい」「実装したい」

次の順で判定する。

1. Task ID、変更ファイル、受け入れ条件が明確か。
2. 明確なら`unity-implement`。
3. 新機能で要件が曖昧なら`unity-specify`。
4. 複数Subsystemへ跨るなら`unity-production-workflow`からFeature lane。

### 「直したい」「壊れた」「エラーが出る」

原因が確定しているかで分ける。

- 原因未確定: `unity-incident-investigation`
- Confirmed Findingと修正境界がある: `csharp-safe-patch`、`shader-performance-refactor`、または`unity-implement`

### 「軽くしたい」「最適化したい」

1. 指標と計測条件があるか確認する。
2. Read-only Auditを先に選ぶ。
3. 主要仮説を一つに絞る。
4. 修正後にEvidence Skillへ渡す。

### 「どう思う」「評価して」「レビューして」

- コード変更なし: `unity-review`または対象Audit Skill
- 仕様書の実現性: `unity-review`
- 性能断定が含まれる: Evidence不足を明示する

### 「原因を教えて」

- 既にログと因果が明確: Explanation lane
- 複数仮説が残る: `unity-incident-investigation`
- ファイル変更を勝手に開始しない

## Conflict resolution

複数Skillが候補になる場合、次の優先順位でPrimaryを決める。

1. **User-requested outcome** — 調査、実装、レビュー、計測のどれを求めているか。
2. **Current evidence state** — 原因未確定なら実装より調査を優先する。
3. **Mutation boundary** — Read-only依頼でModifierを選ばない。
4. **Domain boundary** — Rendering固有問題を汎用C#だけで処理しない。
5. **Verification requirement** — 性能主張はEvidence Skillを必須にする。

Primaryは一つにする。Secondary SkillはPrimaryの不足を補う条件付き参照とする。

## Routing examples

| Prompt | Expected Primary | Reason |
|---|---|---|
| 「このRendererFeatureが何をしているか説明して」 | `unity-production-workflow`のExplanation lane | 変更不要 |
| 「Unity 6でこの例外を直して」 | `unity-incident-investigation` | 原因未確定 |
| 「UJCW-030-001だけ実装して」 | `unity-implement` | Task境界が明確 |
| 「TransparentのOverdrawを軽くしたい」 | `shader-performance-auditor`または`unity-rendering` | 先に対象と証拠を確定 |
| 「このShaderのifを全部消して」 | `shader-performance-auditor` | 一律修正を拒否し監査 |
| 「この変更でSwitchが速くなったか判定して」 | `shader-runtime-evidence`または`unity-runtime-evidence` | 実機Before/Afterが必要 |
| 「新しいTAA補助機能の仕様を作って」 | `unity-specify` | Spec成果物 |
| 「Specから実装手順を作って」 | `unity-plan` | 設計と依存関係 |
| 「PRをレビューして」 | `unity-review` | 受入Gate |

## Guardrails

- ユーザーが指定したTaskより先へ進まない。
- Read-only依頼でファイルを変更しない。
- 原因未確定のIncidentで複数箇所を同時修正しない。
- RendererFeatureの問題へ無関係なControllerを追加しない。
- Shader性能を命令数やソース行だけで確定しない。
- Editor確認だけでPlayer、IL2CPP、Console実機を保証しない。

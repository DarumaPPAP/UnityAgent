# Unity Skill Routing

Unity依頼を、ユーザー表現だけでなく現在State、証拠状態、変更境界から専門Skillへルーティングするための正本表。
複数工程が混在する場合は`unity-production-workflow`をSupervisorとして使い、各状態でPrimary Skillを一つだけ選ぶ。

状態定義と遷移規則は`SkillReferences/UNITY_AGENT_SUPERVISOR_MODEL.md`を参照する。

## 1. Entry routing

| User intent / observed state | Initial state | Primary Skill | Secondary Skill | Do not start with |
|---|---|---|---|---|
| Unityの新機能を作りたい。要件が未整理 | `READY` -> `PLANNING` | `unity-specify` | `unity-production-workflow` | `unity-implement` |
| Specはある。構造と依存関係を決めたい | `PLANNING` | `unity-plan` | 対象Domain Skill | `unity-implement` |
| Planを実行単位へ分解したい | `PLANNING` | `unity-tasks` | なし | `unity-implement` |
| Task ID、変更範囲、受け入れ条件が明確 | `IMPLEMENTING` | `unity-implement` | 対象Domain Skill | `unity-specify` |
| 原因不明のコンパイルエラー、例外、回帰 | `INVESTIGATING` | `unity-incident-investigation` | C# / Rendering / Shader specialist | 大規模リファクタリング |
| Unity C#を変更せず監査したい | `STATIC_VALIDATION` | `csharp-antipattern-audit` | `unity-runtime-evidence` | `csharp-safe-patch` |
| 確定したC# Findingを最小修正したい | `IMPLEMENTING` | `csharp-safe-patch` | `unity-review` | 新規設計 |
| URP / RenderGraph / RendererFeatureを設計・実装 | `PLANNING`または`DOMAIN_VALIDATION` | `unity-rendering` | `unity-plan` / `unity-implement` | 汎用C# Skillだけ |
| 美しいScene、Lighting、LookDev、Composition、Hero Shotを設計 | `READY`または`PLANNING` | `unity-visual-direction` | `unity-specify` / `unity-rendering` | Definition未取得のScene実装 |
| 生成Sceneが美しいかReference基準で評価 | `EVIDENCE_REVIEW` | `unity-visual-direction` | `unity-review` | Compile成功だけの承認 |
| Shader / HLSLの負荷・危険箇所を監査 | `DOMAIN_VALIDATION` | `shader-performance-auditor` | `shader-runtime-evidence` | `shader-performance-refactor` |
| 確定したShader Findingを修正 | `IMPLEMENTING` | `shader-performance-refactor` | `unity-review` | 未計測の全面最適化 |
| Keyword、Variant、Strip、Strict Variant | `DOMAIN_VALIDATION` | `unity-shader-variant-governor` | `shader-runtime-evidence` | 無関係なShader表現変更 |
| C#変更のCPU / GC / Player / 実機Before-After | `VISUAL_OR_RUNTIME_VALIDATION` | `unity-runtime-evidence` | `unity-review` | 静的推測だけの承認 |
| Shader / GPU変更のBefore-After | `VISUAL_OR_RUNTIME_VALIDATION` | `shader-runtime-evidence` | `unity-review` | ソース行数だけの判定 |
| 完成した変更を受入レビュー | `EVIDENCE_REVIEW` | `unity-review` | 対象Audit / Evidence Skill | 新規機能追加 |
| 本番コードへ最小限の日本語コメント | `IMPLEMENTING` | `production-code-comments` | `comment-quality-reviewer` | `learning-code-comments` |
| 学習用に詳しい日本語コメント | `IMPLEMENTING` | `learning-code-comments` | `comment-quality-reviewer` | `production-code-comments` |
| 複数工程、自己検証、PRまで含む依頼 | `INTAKE` | `unity-production-workflow` | StateごとのPrimary Skill | 全Skill / 全Tool一括読込 |
| 単純なコード説明 | なし、またはRead-only `READY` | none / explanation | 必要なDomain参照のみ | Spec / Plan / Mutation |

## 2. Execution Contract routing

Supervisorへ渡された複合依頼は、先に次を確定する。

1. **Goal** — 最終的に成立させる状態
2. **Constraints** — 環境、互換性、変更範囲、禁止事項
3. **Observability** — Static、Unity、Domain、Runtimeの判定方法
4. **Recovery** — 失敗分類ごとの戻り先、停止、Revert

Goalを「コードを生成する」「ファイルを更新する」だけにしない。
ObservabilityのないGoalは完了条件にしない。

Visual taskではGoalへ感情と体験、ObservabilityへVisual Intent、Capture、Beauty Review、Human approvalを含める。

## 3. State-based routing

| Current state | 判断 | Primary route | Output |
|---|---|---|---|
| `INTAKE` | 成果物、変更可否、対象範囲を分類 | `unity-production-workflow` | Work Contract候補 |
| `CONTEXT_REQUIRED` | 何が不足し、どこから取得できるか | Search / Read / 人間確認 | 不足情報一覧 |
| `READY` | 直接実装可能か、設計が必要か、調査が必要か | Implement / Plan / Incident / Visual Direction | Execution Contract |
| `PLANNING` | Spec、Plan、Tasks、Visual Intentのどこまで必要か | `unity-specify` / `unity-plan` / `unity-tasks` / `unity-visual-direction` | 承認可能な計画 |
| `INVESTIGATING` | Expected / Actual / Trigger / Scope / Evidence | `unity-incident-investigation` | Confirmed Hypothesisまたは追加観測 |
| `IMPLEMENTING` | Task、Finding、仮説を一つに限定 | Safe Modifier | 最小Patch |
| `STATIC_VALIDATION` | 規約、差分、互換性、Scope | Audit / `unity-review` | Static findings |
| `UNITY_VALIDATION` | Compile、Console、Test、Play | Unity実行Tool / Incident | Unity evidence |
| `DOMAIN_VALIDATION` | Rendering、Shader、Variant、AOT、Visual contract等 | Domain specialist | Domain evidence |
| `VISUAL_OR_RUNTIME_VALIDATION` | Screenshot、Player、実機、Profiler | Evidence Skill / `unity-visual-direction` | RuntimeまたはVisual evidence |
| `EVIDENCE_REVIEW` | Goalと証拠が一致するか | `unity-review` / `unity-visual-direction` | Accept / Rework / Revert / Inconclusive |
| `AWAITING_HUMAN_DECISION` | 仕様または破壊的変更判断 | 人間 | 承認または方針変更 |
| `AWAITING_HUMAN_APPROVAL` | 機械検証後の最終承認 | 人間 | Accept / Rework |
| `REVERT_REQUIRED` | 回帰、安全条件違反、Scope違反 | Revert / Patch縮小 | 復元結果 |
| `BLOCKED` | 外部証拠または権限がない | 停止 | Block reason |

## 4. Failure routing

失敗は一律に`unity-implement`へ戻さない。

| Failure class | Return state | Primary Skill | Required evidence | Must not |
|---|---|---|---|---|
| C# compile failure | `INVESTIGATING` | `unity-incident-investigation` | 最初の根本エラー、対象Assembly、Editor / Player条件 | 周辺の全面書き換え |
| Dependency / asmdef failure | `INVESTIGATING` | `unity-incident-investigation` | 参照方向、Editor / Runtime境界 | asmdefの無計画な追加 |
| Runtime exception | `INVESTIGATING` | `unity-incident-investigation` | Expected / Actual / Trigger / Call path | 例外の握り潰し |
| RenderGraph failure | `INVESTIGATING` | `unity-incident-investigation` | Pass、Resource、実行順、Global state | Compatibility Modeへの逃避 |
| Shader compile failure | `INVESTIGATING` | Shader specialist | Platform、API、Keyword、Pass | 無関係な表現変更 |
| Variant missing | `DOMAIN_VALIDATION` | `unity-shader-variant-governor` | Runtime keyword、Strip、Addressables、Strict | SVCへの全Variant追加 |
| Visual mismatch / rendering defect | `DOMAIN_VALIDATION` | `unity-rendering` / Shader specialist | Before / After、Camera、Render event、Depth / Blend | Compile成功だけの承認 |
| Beauty mismatch / aesthetic rejection | `EVIDENCE_REVIEW` | `unity-visual-direction` | Definition ID、Visual Intent、Capture、Human feedback | Bloom、Fog、Lightの無差別追加 |
| Performance no-gain / regression | `VISUAL_OR_RUNTIME_VALIDATION` | Evidence Skill | 同条件Before / After、sample、Profiler | 静的推測による改善断定 |
| Scope violation | `REVERT_REQUIRED` | `unity-review` | 変更ファイル一覧、仕様との差分 | 対象外差分を残す |
| Contract conflict | `AWAITING_HUMAN_DECISION` | Supervisor | 選択肢、影響、Revert | Agentによる契約変更 |
| Missing tool / unavailable device / unavailable beauty source | `CONTEXT_REQUIRED`または`BLOCKED` | Supervisor | 未取得証拠またはDefinition | 実行済み・取得済みと推測 |

## 5. Intent classifiers

### 「作りたい」「実装したい」

1. Goal、Constraints、Observability、Recoveryが成立しているか。
2. Task ID、変更ファイル、受け入れ条件が明確なら`IMPLEMENTING`。
3. 新機能で要件が曖昧なら`PLANNING`から`unity-specify`。
4. 原因不明の修正を含むなら、実装前に`INVESTIGATING`。
5. 複数工程と自己検証を求められたら`unity-production-workflow`をSupervisorにする。
6. 美的成果を含むなら、実装前に`unity-visual-direction`でVisual Intentを作る。

### 「美しい」「綺麗」「ハイエンド」「画作り」

1. `DarumaPPAP/Beautiful-Definition`を美的正本として取得する。
2. `Catalog/definitions.yaml`から一致するDefinition IDを選ぶ。
3. Visual Intent Contractを作る。
4. Camera、Composition、Lighting、Color、Depth、Material、Post limitを先に確定する。
5. 技術実装は`unity-rendering`または`unity-implement`へ委譲する。
6. Beauty ReviewとTechnical validationを分離する。
7. Human reviewなしに`VISUAL_ACCEPTED`としない。

### 「直したい」「壊れた」「エラーが出る」

- 原因未確定: `INVESTIGATING` / `unity-incident-investigation`
- Confirmed Findingと修正境界がある: `IMPLEMENTING` / Safe Modifier
- 修正後: 失敗種類に対応するValidation Stateへ進む

### 「軽くしたい」「最適化したい」

1. 指標、再現条件、PlatformをObservabilityへ固定する。
2. Read-only Auditを先に選ぶ。
3. 主要仮説を一つに絞る。
4. 最小Patch後にEvidence Skillへ渡す。
5. Adopt / Rework / Revert / Inconclusiveで判定する。

### 「全部任せる」「自走して」「完成まで」

- `unity-production-workflow`をSupervisorにする。
- 自動化対象は調査、実装、利用可能なToolによる検証、証拠整理まで。
- 公開契約変更、品質トレードオフ、ファイル削除、Mergeは人間判断へ分離する。
- Toolがない検証を実行済みと扱わない。
- 美的承認は人間へ引き渡す。

### 「どう思う」「評価して」「レビューして」

- コード変更なし: `EVIDENCE_REVIEW`または対象Audit Skill
- 仕様書の実現性: `unity-review`
- 美的評価: `unity-visual-direction`
- 性能断定を含む: Evidence不足を明示する

### 「原因を教えて」

- 因果が既に明確: Explanation
- 複数仮説が残る: `INVESTIGATING`
- ファイル変更を勝手に開始しない

## 6. Conflict resolution

複数Skillが候補になる場合は次の順でPrimaryを一つ決める。

1. **User-requested outcome** — 説明、調査、実装、レビュー、計測、Visual direction
2. **Current state** — Planning、Investigating、Implementing、Validation
3. **Evidence state** — 原因未確定なら実装より調査を優先
4. **Mutation boundary** — Read-only依頼でModifierを選ばない
5. **Domain boundary** — Rendering固有問題を汎用C#だけで処理しない
6. **Visual authority** — 美的判断はBeautiful-DefinitionとUser instructionを優先
7. **Verification requirement** — 性能主張はEvidence Skillを必須にする
8. **Human boundary** — 破壊的契約、Merge、Visual acceptanceをAgentだけで決定しない

Secondary SkillはPrimaryの不足を補う条件付き参照とする。

## 7. Routing examples

| Prompt | Expected route | Reason |
|---|---|---|
| 「このRendererFeatureが何をしているか説明して」 | Explanation / `unity-rendering`参照 | 変更不要 |
| 「Unity 6でこの例外を直して」 | `INVESTIGATING` / `unity-incident-investigation` | 原因未確定 |
| 「UJCW-030-001だけ実装して」 | `IMPLEMENTING` / `unity-implement` | Task境界が明確 |
| 「TransparentのOverdrawを軽くして実機確認まで」 | Supervisor -> Audit -> Implement -> Runtime Evidence | 複数Stateが必要 |
| 「このShaderのifを全部消して」 | `DOMAIN_VALIDATION` / `shader-performance-auditor` | 一律修正を拒否 |
| 「新しいTAA補助機能の仕様を作って」 | `PLANNING` / `unity-specify` | Spec成果物 |
| 「Beautiful-Definitionを参照して美しい海辺Sceneを設計して」 | `PLANNING` / `unity-visual-direction` | Definition取得とVisual Intentが先 |
| 「このCaptureが美しいか評価して」 | `EVIDENCE_REVIEW` / `unity-visual-direction` | Beauty gateとHuman reviewが必要 |
| 「コードを書いてUnityでエラーを直し、証拠付きでPRにして」 | `unity-production-workflow` | 自己検証と複数工程 |
| 「コンパイルは通ったが表示が違う」 | `DOMAIN_VALIDATION` | Compile failureではなくVisual failure |
| 「EditorはOK、Switch未確認」 | `CONTEXT_REQUIRED`またはEvidence Required | 実機未検証 |

## 8. Guardrails

- ユーザーが指定したTaskより先へ進まない。
- Read-only依頼でファイルを変更しない。
- 原因未確定のIncidentで複数箇所を同時修正しない。
- RendererFeatureの問題へ無関係なControllerを追加しない。
- Shader性能を命令数やソース行だけで確定しない。
- Compile成功だけでVisual、Player、Console実機を保証しない。
- Feature数、Light数、Bloom、Fogを美しさとして扱わない。
- Beautiful-Definition未取得でUserの美的好みを推測しない。
- Human reviewなしに`VISUAL_ACCEPTED`としない。
- 失敗種類に関係なく同じAgentへ戻さない。
- 全Skill、全Reference、全Toolを一括で読み込まない。
- 指定Task完了後に次Taskへ自動で進まない。
- PR Mergeは明示された人間判断なしに行わない。

# UnityAgent Domain Bootstrap

UnityAgentはUnity / C# / URP / RenderGraph / Shader / Performance / Visual DirectionのDomain Knowledge正本です。汎用の実行モード、Task Graph、Retry、Token Budget、Checkpointは`DarumaPPAP/Unity-Graph-Engineering`が所有します。

## 1. Workspace

- このRepositoryはUnityプロジェクト本体ではない。
- `Assets/`、`Packages/`、`ProjectSettings/`を推測で作成しない。
- 製品コード、製品仕様、導入資料は`DarumaPPAP/UnityAIGC-Archive`へ保存する。
- `Reference/`はRead-only。
- 美的正本は`DarumaPPAP/Beautiful-Definition`。
- Google Driveは大容量資料と閲覧用Reference。編集正本はGitHub。

## 2. Execution ownership

Execution Modeが未指定の場合はUnity-Graph-EngineeringのPolicyによりPrompt Engineeringを使用する。Graph / Loopへの無断変更は禁止する。

UnityAgentは次だけを担当する。

- Domain route
- Context Pack
- Unity固有の実装・監査手順
- Unity固有ValidatorとEvidence要求

次は担当しない。

- 汎用Supervisor State Machine
- 汎用Task Graph
- Retry Scheduler
- Token Accounting
- Human Gate orchestration

Compatibility adapter:

- `.agents/skills/unity-production-workflow/SKILL.md`
- `SkillReferences/UNITY_AGENT_SUPERVISOR_MODEL.md`

## 3. Context routing

最初に`.ai/context-index.yaml`を読み、依頼に一致するContext Packを一つ選ぶ。

- 全Skillを一括で読まない。
- 全Referenceを一括で読まない。
- Primary Domain Skillは一つ。
- Conditional Referenceは条件成立時だけ読む。
- 対象Sourceと直接依存を優先する。
- Knowledge Graphは候補Artifactの絞り込みにだけ使い、変更前にSourceを直接読む。

Context Pack:

- `.ai/context-packs/csharp-local-fix.yaml`
- `.ai/context-packs/rendering-incident.yaml`
- `.ai/context-packs/shader-change.yaml`
- `.ai/context-packs/performance.yaml`
- `.ai/context-packs/visual-direction.yaml`

## 4. Project facts

対象Repositoryの既存コード、asmdef、Project Context、Feature Specから次を確定する。

- Unity Version
- Render Pipeline / Version
- RenderGraph
- Platform / Graphics API
- Editor / Player
- Mono / IL2CPP
- Burst / Jobs / Entities
- Root Namespace
- Build / Test方法
- 実機Evidenceの有無

Repositoryから確定できる情報を質問し直さない。確認できない条件は推測せず未検証とする。

## 5. Non-negotiable C# constraints

- 既存コード変更では既存namespaceを保持する。
- Root Namespaceありは`<RootNamespace>.<FeatureName>`、なしは`<FeatureName>`。
- `Namespace`、`RootNamespace`、`CHANGE_ME`、先頭・末尾`.`を実出力しない。
- private fieldは`_camelCase`。
- enumは`E_UPPER_SNAKE_CASE`。
- structは必要時のみ`S_UPPER_SNAKE_CASE`、原則`readonly struct`。
- constは`SCREAMING_SNAKE_CASE`。
- Runtimeから`UnityEditor` APIを参照しない。
- Editor機能はEditor FolderまたはEditor-only Assemblyへ隔離する。
- MonoBehaviourは1 File 1 Type。
- asmdefは境界が必要な場合だけ追加する。
- mutable static状態、static event、Singleton、Service Locatorを安易に追加しない。
- 不要なController、Manager、Setup、自動探索、Fallback、Cache、Debug UIを追加しない。
- public API、SerializeField、Prefab、Scene、Save Data互換性を無断変更しない。
- コメントは日本語で意図、制約、危険箇所を書く。

詳細は選択Context Packから対応Referenceを読む。

## 6. Rendering / Shader constraints

- Unity / URP Versionを確認せず別VersionのAPIを移植しない。
- RendererFeatureではInjection Point、Queue、Layer、ShaderTag、Sorting、Resource read/writeを確認する。
- RenderGraphとCompatibility APIを無計画に混在させない。
- Shader名、Property、Keyword、Pass、LightMode、RenderState、CBUFFERを無断変更しない。
- 新Pass追加より既存Pass、RendererList filtering、RenderQueue、Layer、ShaderTagを先に検討する。
- Motion Vector、Depth、History UV、Reprojection、Disocclusionを安易に低精度化しない。
- `if`、`loop`、`half`、`discard`を一律禁止しない。
- Shader PatternだけでGPU時間を断定しない。
- Variant削減前にRuntime Keyword、Addressables、AssetBundle、Resources、Strict Variantを確認する。
- Editor結果だけでPlayer、Switch、Console実機を保証しない。

## 7. Audit, mutation, evidence

- Read-only AuditとMutationを分離する。
- 原因未確定のIncidentで複数箇所を同時変更しない。
- 一つのPatchにつきTask、Confirmed Finding、主要仮説のいずれか一つを扱う。
- 性能変更はBefore / After、品質条件、Revert条件を持つ。
- Compile成功だけでRuntime、Visual、Performance、実機を承認しない。
- AIの自己申告だけをEvidenceにしない。

## 8. Visual boundary

美しいScene、Lighting、Composition、Color、Atmosphere、Camera presentationでは`unity-visual-direction`を使用し、必要なBeautiful-Definitionだけを取得する。

- Visual Intentなしに美しさを推測しない。
- Compile、Capture生成、Light数、Bloom、FogをBeauty Evidenceにしない。
- Human reviewなしに`VISUAL_ACCEPTED`としない。
- 固有Character、Logo、Architecture、配置を直接複製しない。

## 9. Generated artifacts

UnityAgentを参照して生成した製品FeatureはUnityAIGC-Archiveへ保存する。UnityAgent内の製品Feature用`Implementation/`または`Specs/`へ新規生成しない。

## 10. Completion contribution

Domain SkillはExecution Ownerへ次を返す。

- Confirmed context
- 適用したContext Pack
- Domain findings
- Mutation constraints
- Required validation
- Evidence status
- 未検証事項
- Compatibility / Revert条件

実行モード、Graph State、Budget、Human Gateの最終管理はUnity-Graph-Engineeringへ委譲する。

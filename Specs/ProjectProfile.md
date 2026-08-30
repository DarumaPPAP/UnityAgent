# Project Profile

このProfileは、対象Unity Projectへ接続できない場合や必要なProject Factを直接確認できない場合に使用するFallbackです。常時読み込む正本ではありません。

対象Unity Projectへ接続できる場合、Unity Version、Pipeline、Rendering Path、Build Target、namespace等の検出済み事実をこのProfileより優先します。今回ユーザーが確認したProject FactもこのProfileより優先します。このProfileの値はMyUnityMCP全体の固定対応条件ではありません。

このProfileを編集する場合も、検出済みFactの代替ではなく「未解決Factを補うためのProject固有Fallback」として管理します。

## Identity

- ProjectName: CHANGE_ME
- RootNamespace: NONE

`RootNamespace`には、実際に使用するRoot Namespaceか`NONE`を設定する。

Namespace規則:

- `RootNamespace`が実名の場合: `<RootNamespace>.<FeatureName>`
- `RootNamespace: NONE`の場合: `<FeatureName>`
- 既存コードを変更する場合: 既存namespaceを保持する
- `.Runtime`、`.Editor`、`.Rendering`などの追加階層は既存Project規約または実在するAssembly/ownership boundaryがある場合だけ導入する

`Namespace`、`RootNamespace`、`<RootNamespace>`、`CHANGE_ME`を実際のnamespaceやasmdef名として出力してはならない。先頭または末尾が`.`のnamespaceも禁止する。

## Unity environment

以下はこのProfileをFallbackとして使用するProjectの補助設定値です。MyUnityMCPのGlobal DefaultまたはSupport Contractとして使用しません。

- UnityVersion: 6000.3
- RenderPipeline: URP 17+
- RenderGraph: Enabled
- RenderingPath: Forward
- RuntimePlatformPolicy: Platform-independent
- PlatformDependencies: None by default
- ExplicitPlatformIntegrations: None
- PerformanceClass: Low-spec console class
- PerformanceReferenceExample: Nintendo Switch-equivalent constraints
- XR: Not targeted

`PerformanceReferenceExample`はCPU、GPU、Memory、Bandwidth、Frame Budgetの目安であり、対応Platform、Build Target、SDK依存、Module依存、専用define、完了条件を意味しない。

特定Platform名は、次の場合だけ`ExplicitPlatformIntegrations`へ追加する。

- Platform SDK、Platform API、専用Package、専用defineを使用する
- Platform固有Buildを成果物として要求する
- Platform固有の互換性または性能を保証する

単に「Nintendo Switchでも動く程度に軽くする」場合はPlatform IntegrationではなくPerformance Classとして扱う。

Environment情報の優先順位:

1. 対象Unity Projectから検出した事実
2. 今回ユーザーが確認したProject Factと明示した実装依存・制約
3. Project固有Context
4. このProject Profile
5. UnityAgentの既定Preference

Project Profileを使用する場合は、どの未解決Factを補うために読んだかを明確にする。検出済みFactとProfileが競合した場合は検出済みFactを採用し、Profile側を自動的に正本へ昇格させない。

Platform Build TargetとPerformance Targetを混同しない。Target Platformが未指定でも、Platform非依存の設計、実装、検証を継続する。

## Workspace / Repository boundary

- UnityAgentRepository: `DarumaPPAP/UnityAgent`
- McpRepository: `DarumaPPAP/MyUnityMCP`
- McpSpecificationRoot: `DarumaPPAP/MyUnityMCP/Specs/`
- McpPackageRoot: `DarumaPPAP/MyUnityMCP/Packages/`
- McpCatalogRoot: `DarumaPPAP/MyUnityMCP/Catalog/`
- GeneratedProductRepository: `DarumaPPAP/UnityAIGC-Archive`
- ImplementationRoot: `DarumaPPAP/UnityAIGC-Archive/Implementation/`
- GeneratedSpecRoot: `DarumaPPAP/UnityAIGC-Archive/Specs/`
- GovernanceSpecRoot: `Specs/`
- UnityProjectPath: user-managed
- AutomaticFileSync: Disabled
- AutomaticCodeScan: Disabled

通常の製品コード、製品仕様、導入資料は`GeneratedProductRepository`へ保存する。

UnityAgentが利用するMCP本体、Creator Workflow、Domain MCP、Capability Module、Manifest、Tool Schema、MCP固有仕様は`McpRepository`へ保存する。MCP関連の製品正本を`UnityAIGC-Archive`へ保存しない。

MCPが生成または変更したScene、Prefab、Material、Timeline、Volume Profile等は対象Unity Projectが所有する。

UnityAgent自身が所有するのは、個別MCP製品実装ではなく、UnityAgentのProduction authorityです。現在の主なcanonical surfaceは次です。

- `Policy/` — User / Risk / Security / Approval / Evidence rules
- `Orchestration/` — Route / Graph / Task Contract / Runtime handoff
- `Context/` — Context Pack / Retrieval / Budget / Materialization / MCP selection
- `Runtime/` — Execution / Guardrails / Permissions / Harness / Telemetry
- `Persistence/` — durable State / Checkpoint / Resume / Memory / Evidence
- `Operations/` — Observability / Detection / Incident / approved control / ChangeManagement
- `Eval/` — Golden / Behavior / Replay / Rebaseline / Regression
- `.agents/skills/` / `SkillReferences/` — selected domain procedure / supporting rule

MCP PackageやMCP製品仕様そのものをUnityAgentへ複製しない。UnityAgent側にはMCPを選択・制約・検証するためのcontractだけを保持する。

## Project-specific preferences

- InspectorとEditor Windowは日本語を優先する。
- Editor UIは黒基調、文字は白を基本とする。
- staticの乱用を避ける。
- Scene上のControllerや外部Profileは要件がある場合だけ導入する。
- Shader名に`Hidden/`を安易に使用しない。
- Camera Stackを前提にしない。

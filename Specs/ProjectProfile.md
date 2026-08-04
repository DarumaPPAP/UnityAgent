# Project Profile

プロジェクトごとに最初に編集してください。AIはこの内容を環境の正として扱います。

## Identity

- ProjectName: CHANGE_ME
- RootNamespace: NONE

`RootNamespace`には、実際に使用するRoot Namespaceか`NONE`を設定する。

Namespace規則:

- `RootNamespace`が実名の場合: `<RootNamespace>.<FeatureName>`
- `RootNamespace: NONE`の場合: `<FeatureName>`
- 既存コードを変更する場合: 既存namespaceを保持する
- `.Runtime`、`.Editor`、`.Rendering`などの追加階層は禁止する

`Namespace`、`RootNamespace`、`<RootNamespace>`、`CHANGE_ME`を実際のnamespaceやasmdef名として出力してはならない。先頭または末尾が`.`のnamespaceも禁止する。

## Unity environment

- UnityVersion: 6000.3
- RenderPipeline: URP 17+
- RenderGraph: Enabled
- RenderingPath: Forward
- PrimaryPlatform: Nintendo Switch
- OtherPlatforms: Nintendo Switch 2 / PlayStation 4 / PlayStation 5 / PC
- XR: Not targeted

## Workspace policy

- KnowledgeRepository: `DarumaPPAP/UnityAgent`
- McpRepository: `DarumaPPAP/MyUnityMCP`
- McpSpecificationRoot: `DarumaPPAP/MyUnityMCP/Specs/`
- McpPackageRoot: `DarumaPPAP/MyUnityMCP/Packages/`
- McpCatalogRoot: `DarumaPPAP/MyUnityMCP/Catalog/`
- GeneratedProductRepository: `DarumaPPAP/UnityAIGC-Archive`
- ImplementationRoot: `DarumaPPAP/UnityAIGC-Archive/Implementation/`
- GeneratedSpecRoot: `DarumaPPAP/UnityAIGC-Archive/Specs/`
- ReferenceRoot: `Reference/`
- GovernanceSpecRoot: `Specs/`
- UnityProjectPath: user-managed
- AutomaticFileSync: Disabled
- AutomaticCodeScan: Disabled

通常の製品コード、製品仕様、導入資料は`GeneratedProductRepository`へ保存する。

UnityAgentが利用するMCP本体、Creator Workflow、Domain MCP、Capability Module、Manifest、Tool Schema、MCP固有仕様は`McpRepository`へ保存する。MCP関連の正本を`UnityAIGC-Archive`へ保存しない。

MCPが生成または変更したScene、Prefab、Material、Timeline、Volume Profile等は対象Unity Projectが所有する。

UnityAgentにはRoute、Context Pack、Task Contract、Knowledge Contract、MCP Activation Policyだけを保存する。UnityAgent内へMCP PackageやMCP製品仕様を追加しない。

## Project-specific preferences

- InspectorとEditor Windowは日本語を優先する。
- Editor UIは黒基調、文字は白を基本とする。
- staticの乱用を避ける。
- Scene上のControllerや外部Profileは要件がある場合だけ導入する。
- Shader名に`Hidden/`を安易に使用しない。
- Camera Stackを前提にしない。
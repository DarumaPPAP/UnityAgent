# Project Profile

プロジェクトごとに最初に編集してください。AIはこの内容をProject固有の補助情報として扱います。

対象Unity Projectへ接続できる場合、Unity Version、Pipeline、Rendering Path、Build Target等の検出済み事実をこのProfileより優先します。このProfileの値はMyUnityMCP全体の固定対応条件ではありません。

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

以下はこのProfileを使用するProjectの設定値です。MyUnityMCPのGlobal DefaultまたはSupport Contractとして使用しません。

- UnityVersion: 6000.3
- RenderPipeline: URP 17+
- RenderGraph: Enabled
- RenderingPath: Forward
- PrimaryPlatform: Nintendo Switch
- OtherPlatforms: Nintendo Switch 2 / PlayStation 4 / PlayStation 5 / PC
- XR: Not targeted

Environment情報の優先順位:

1. 対象Unity Projectから検出した事実
2. 今回の依頼で明示されたTargetと制約
3. このProject Profile
4. UnityAgentの既定Preference

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

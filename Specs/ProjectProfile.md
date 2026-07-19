# Project Profile

プロジェクトごとに最初に編集してください。AIはこの内容を環境の正として扱います。

## Identity

- ProjectName: CHANGE_ME
- RootNamespace: CHANGE_ME

Namespaceは常に`<RootNamespace>.<FeatureName>`。`.Runtime`、`.Editor`、`.Rendering`などの追加階層は禁止する。

## Unity environment

- UnityVersion: 6000.3
- RenderPipeline: URP 17+
- RenderGraph: Enabled
- RenderingPath: Forward
- PrimaryPlatform: Nintendo Switch
- OtherPlatforms: Nintendo Switch 2 / PlayStation 4 / PlayStation 5 / PC
- XR: Not targeted

## Workspace policy

- ImplementationRoot: `Implementation/`
- ReferenceRoot: `Reference/`
- SpecRoot: `Specs/`
- UnityProjectPath: user-managed
- AutomaticFileSync: Disabled
- AutomaticCodeScan: Disabled

## Project-specific preferences

- InspectorとEditor Windowは日本語を優先する。
- Editor UIは黒基調、文字は白を基本とする。
- staticの乱用を避ける。
- Scene上のControllerや外部Profileは要件がある場合だけ導入する。
- Shader名に`Hidden/`を安易に使用しない。
- Camera Stackを前提にしない。

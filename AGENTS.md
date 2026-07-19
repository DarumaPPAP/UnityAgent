# Unity AI Workspace Instructions

## Workspace

- このリポジトリはUnityプロジェクト本体ではなく、AI実装・設計・監査用ワークスペースである。
- `Assets/`、`Packages/`、`ProjectSettings/`を推測で作成しない。
- 製品コードは`Implementation/`内だけに作成・変更する。
- `Reference/`は読み取り専用とする。
- Unityプロジェクトへのコピーや配置はユーザーが行う。

## Required reading

1. `Specs/ProjectProfile.md`
2. `Specs/ProjectConstitution.md`
3. 対象機能の`Specs/<FeatureName>/spec.md`
4. 対応する`.agents/skills/<skill-name>/SKILL.md`
5. C#作業では`SkillReferences/CODING_STANDARDS.md`
6. 設計変更では`SkillReferences/ARCHITECTURE_STANDARDS.md`
7. C#品質監査では`SkillReferences/CSHARP_ANTIPATTERN_RULES.md`と`CSHARP_ANTIPATTERN_POLICY.md`
8. Rendering作業では`SkillReferences/RENDERING_STANDARDS.md`

## Spec-driven workflow

- 仕様がない新機能は最初に`unity-specify` SkillでSpecを作る。
- 実装前に`spec.md`、`plan.md`、`tasks.md`を揃える。
- 仕様にない設定、Controller、Manager、Debug機能を追加しない。
- 仮定は`decisions.md`へ記録する。
- 変更は対象Taskに必要な最小範囲へ限定する。

## C# quality gate

対象Unity、Render Pipeline、Platform、Editor/Player、Mono/IL2CPP、Development/Release、Burst/Jobs/Entities、呼び出し頻度、APIとシリアライズ互換性を先に確定する。

判断順序:

1. 仕様・意味論・所有権・寿命
2. バグ・AOT・スレッド・セキュリティ
3. Allocation・コピー・boxing・同期・描画頻度
4. 計測証拠
5. 自動修正の互換性

静的に確定できる問題と実行時計測が必要な問題を分離する。

## Non-negotiable coding constraints

- Namespaceは`<RootNamespace>.<FeatureName>`の2階層。
- privateフィールドは`_camelCase`。
- enum型名は`E_UPPER_SNAKE_CASE`。
- struct型名は`S_UPPER_SNAKE_CASE`。原則`readonly struct`。
- constは`SCREAMING_SNAKE_CASE`。
- mutable static状態、static event、Singleton、Service Locatorを追加しない。
- `Manager`、`Controller`、`Util`、`Common`、`Helper`を責務説明なしで作らない。
- 公開`async void`、`Task.Result`、`.Wait()`、`throw ex;`、空catch、`BinaryFormatter`を新規導入しない。
- Burst/Jobsへmanaged object、managed array、暗黙boxing、所有権不明なNativeContainerを持ち込まない。
- Reflection、dynamic、実行時ジェネリック生成はIL2CPP/AOT/stripping条件を確認する。
- コメントは日本語で理由・制約・意図を書く。

## Shader / HLSL quality gate

ShaderLab、HLSL、Compute Shader、Shader Graph Custom Function、RendererFeature、RenderGraph、Shader Variantを扱う場合は次を読む。

1. `SkillReferences/SHADER_PERFORMANCE_STANDARDS.md`
2. `SkillReferences/ShaderPerformance/UNITY_URP_POLICY.md`
3. `SkillReferences/ShaderPerformance/SHADER_REVIEW_GATE.md`
4. 対応Skill
5. 監査時は`RULE_CATALOG.md`
6. 修正時は`REFACTOR_POLICY.md`
7. Variant変更時は`VARIANT_POLICY.md`

作業順序:

`Context Resolution -> Read-only Audit -> Variant Audit -> Runtime Evidence -> Safe Refactor -> Review Gate`

- ソースパターンだけでGPU時間を断定しない。
- `if`、`loop`、`half`、`discard`を一律禁止しない。
- Scanner結果を確定診断にしない。
- Shader名、Property、Keyword、Pass、LightMode、RenderState、CBUFFERを無断変更しない。
- 新Pass追加よりRendererFeature、RenderQueue、Layer、ShaderTag、RendererList、既存Pass再利用を先に検討する。
- Motion Vector、Depth、History UV、Reprojection、Disocclusion、Reactive Maskを安易に低精度化しない。
- Variant削減前にRuntime Keyword、Addressables、AssetBundle、Resources、Strict Variantを確認する。
- 1 Patchにつき主要仮説は1つ。Before/AfterとRevert条件を記録する。
- Editor結果だけでTarget Player、Console、Switch実機を保証しない。

## Completion report

- 変更ファイル
- Task ID
- 仕様との差異
- 重大なFindingと対応
- Unity側の確認事項
- 未検証事項

Unityでコンパイルしていない場合は動作確認済みと表現しない。実機未計測なら性能改善を確定表現しない。

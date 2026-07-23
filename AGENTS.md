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
3. 入口が不明な複合依頼では`SkillReferences/UNITY_SKILL_ROUTING.md`
4. 対象機能の`Specs/<FeatureName>/spec.md`
5. Primaryとして選択した`.agents/skills/<skill-name>/SKILL.md`
6. C#作業では`SkillReferences/CODING_STANDARDS.md`
7. 設計変更では`SkillReferences/ARCHITECTURE_STANDARDS.md`
8. C#品質監査では`SkillReferences/CSHARP_ANTIPATTERN_RULES.md`と`CSHARP_ANTIPATTERN_POLICY.md`
9. Rendering作業では`SkillReferences/RENDERING_STANDARDS.md`

全Skillと全Referenceを一括で読み込まない。Primary Skillを一つ選び、そのSkillが条件付きで委譲する資料だけを読む。

## Skill routing

- 複数工程が混在する依頼は`unity-production-workflow`を入口にする。
- 原因不明のエラー、回帰、Editor/Player差、描画破綻は`unity-incident-investigation`をPrimaryにする。
- Read-only監査と修正を分離する。
- 原因未確定のIncidentで複数箇所を同時変更しない。
- 性能作業は`Audit -> Single Hypothesis -> Minimal Patch -> Runtime Evidence`の順にする。
- Primary Skillは一つにする。Secondary Skillは不足する専門領域だけを補う。

## Ceremony budget

- 新機能または複数Subsystemへ跨る仕様変更は`unity-specify -> unity-plan -> unity-tasks -> unity-implement -> unity-review`を使う。
- 単一ファイルの局所修正で、要件、変更範囲、受け入れ条件が明確な場合は、形式的なSpec/Plan/Tasksを増やさない。
- 性能変更は規模に関係なくBefore/After条件とRevert条件を先に持つ。
- 長期保存が必要なIncidentだけを`Specs/<FeatureName>/incidents/`へ記録する。

## Spec-driven workflow

- 仕様がない新機能は最初に`unity-specify` SkillでSpecを作る。
- 複数責務または複数ファイルへ跨る実装前に`spec.md`、`plan.md`、`tasks.md`を揃える。
- 仕様にない設定、Controller、Manager、Debug機能を追加しない。
- 仮定は`decisions.md`へ記録する。
- 変更は対象Taskに必要な最小範囲へ限定する。
- 選択Taskが完了しても、次Taskへ自動的に進まない。

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

- Namespaceは対象プロジェクトの既存コード、asmdefの`rootNamespace`、または`Specs/ProjectProfile.md`から確定する。
- Root Namespaceが設定済みなら`<RootNamespace>.<FeatureName>`、Root Namespaceなしなら`<FeatureName>`を使用する。
- 既存コードを変更する場合は既存namespaceを保持する。
- `Namespace`、`RootNamespace`、`<RootNamespace>`、`CHANGE_ME`を実際のnamespace、asmdef名、Assembly参照へ出力しない。
- 先頭または末尾が`.`のnamespaceを生成しない。
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

`Context Resolution -> Read-only Audit -> Variant Audit -> Runtime Evidence Plan -> Safe Refactor -> Review Gate`

- ソースパターンだけでGPU時間を断定しない。
- `if`、`loop`、`half`、`discard`を一律禁止しない。
- Scanner結果を確定診断にしない。
- Shader名、Property、Keyword、Pass、LightMode、RenderState、CBUFFERを無断変更しない。
- 新Pass追加よりRendererFeature、RenderQueue、Layer、ShaderTag、RendererList、既存Pass再利用を先に検討する。
- Motion Vector、Depth、History UV、Reprojection、Disocclusion、Reactive Maskを安易に低精度化しない。
- Variant削減前にRuntime Keyword、Addressables、AssetBundle、Resources、Strict Variantを確認する。
- 1 Patchにつき主要仮説は1つ。Before/AfterとRevert条件を記録する。
- Editor結果だけでTarget Player、Console、Switch実機を保証しない。

## Skill authoring

Skillを追加または大幅更新する場合は`SkillReferences/UNITY_SKILL_AUTHORING_STANDARD.md`を読む。

- `description`は`Use when ...`で開始し、発火条件、成果物、非対象を記載する。
- Flow、Audit、Modifier、Evidenceの責務を分離する。
- 長い共通規約をSkillへコピーせず、Referenceへ委譲する。
- `Tests/SkillRouting/cases.yaml`へPositive、Negative、Conflict、Scope、Evidenceケースを追加する。
- `python Tools/SkillValidator/validate_skills.py`で構造を確認する。
- 既存Skillを段階移行する間はadvisory modeを使い、新規Skillは`--strict`で確認する。

## Completion report

- Primary lane / Primary Skill
- 変更ファイル
- Task IDまたはIncident ID
- 仕様との差異
- 重大なFindingと対応
- 保持または変更した互換性契約
- 実施した検証階層
- Unity側の確認事項
- 未検証事項
- Revert条件

Unityでコンパイルしていない場合は動作確認済みと表現しない。実機未計測なら性能改善を確定表現しない。

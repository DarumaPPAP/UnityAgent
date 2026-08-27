---
name: unity-implement
description: Use when a Unity Task, confirmed incident fix, or explicitly bounded file change is ready for implementation. Applies the smallest compatible code or asset-side change, follows the relevant C# or rendering standards, and reports the exact validation level. Does not expand into later Tasks, speculative refactors, or unrequested systems.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  version: "2.4.0"
  kind: operation
  entrypoint: false
  user_policy: .ai/user-policy.yaml
---

# Unity Implement

承認済みTask、Confirmed Incident、または依頼文で完全に境界づけられた局所変更を、最小差分で実装する。
このSkillは「選択された一件の実装」を所有する。
Primary Domain Routeは`.ai/context-index.yaml`で選択済みであることを前提とし、このSkill自身をRouting入口にしない。

## When to use

- Task IDが指定されている
- `spec.md`、`plan.md`、`tasks.md`から実行Taskが選択済み
- Incident調査で根因と最小修正がConfirmed
- 変更対象ファイル、期待結果、禁止事項が依頼文で明確

原因未確定の不具合には`unity-incident-investigation`を使う。
Read-only監査には対応Audit Skillを使う。

## Inputs

優先順に読む。

1. ユーザーが指定したTask ID、ファイル、禁止事項
2. `.ai/user-policy.yaml`
3. 選択済みContext PackとTask Contract
4. Feature `spec.md`、`plan.md`、`tasks.md`
5. 対象コード、直接依存、対象Projectから検出したFact
6. 必要なProject Factが未解決の場合だけ`Specs/ProjectProfile.md`をFallbackとして読む
7. `SkillReferences/ENGINEERING_DESIGN_PRINCIPLES.md`と適用されるCoding / Architecture / Rendering standards
8. `SkillReferences/TYPE_NAMING_STANDARDS.md` when a new Type or explicit Type rename is part of the Task

`Specs/ProjectProfile.md`はProject未接続または必要Factが取得できない場合のFallbackであり、検出済みProject Factや今回ユーザーが確認したFactを上書きしない。
古いPolicy文書を現在のUser Policyへ上書き統合しない。
全Referenceを無条件に読まない。対象変更に必要なものだけを読む。

## Delegates to

- Unity C#監査済みFindingの修正: `csharp-safe-patch`
- URP / RenderGraph / RendererFeature: `unity-rendering`
- Shader/HLSL修正: `shader-performance-refactor`
- Keyword / Variant: `unity-shader-variant-governor`
- 修正後Evidence: `unity-runtime-evidence`または`shader-runtime-evidence`
- 受入レビュー: `unity-review`
- コメント追加: `production-code-comments`または`learning-code-comments`

## Workflow

### Step 1 — Restate the implementation boundary

実装開始前に内部的に次を固定する。

- Task / Incident / Rule ID
- Goal
- Changed files
- Explicit non-goals
- Compatibility contracts
- Validation available

ユーザーが「このTaskだけ」「この3クラスだけ」と指定した場合、その境界を最優先する。

### Step 2 — Inspect current behavior and contracts

- 呼び出し元と呼び出し頻度
- 所有者と寿命
- public API
- SerializeField、Prefab、Scene、Save Data
- Assembly Definition、Editor/Runtime境界
- 既存コードのnamespace
- asmdefの`name`、`rootNamespace`、Assembly参照
- 対象Projectから検出したUnity Version、Pipeline、Platform、Namespace等のFact
- 必要Factが未解決の場合だけ`Specs/ProjectProfile.md`の対応項目
- Shader Property、Keyword、Pass、LightMode、RenderState
- Platform / IL2CPP / Burst / Jobs条件

Namespaceは既存コード、asmdef、検出済みProject Fact、ユーザー確認済みFactから確定する。それでも未解決の場合だけProject ProfileをFallbackにする。Root Namespaceが未設定または不明な場合、`Namespace`、`RootNamespace`、`CHANGE_ME`などを実名として補完しない。

既存コードの意図を確認せず置換しない。

### Step 3 — Select the smallest causal change

- 根因またはTask要件へ直接対応する。
- Existing Ownerで解決できるかを最初に確認する。
- KISSとして`Single Cohesive Script First` / Simplest Cohesive Solutionを適用し、新規クラスより既存責務への局所変更を先に検討する。
- YAGNIとして現在要求に不要なStructureを追加しない。
- 新規C#ファイルには具体的なSplit Reasonを要求する。
- Controller、Manager、Profile、Fallback、Cache、Debug UIを仕様外で追加しない。
- static状態やSingletonへ所有権を逃がさない。
- 別問題を発見しても現在のPatchへ混ぜない。

新規Type / Interface / Fileを追加する場合、次を確認する。

- Existing Ownerへ含められない実在理由がある。
- KISSを満たし、より単純で凝集した候補を先に検討した。
- YAGNI違反のSpeculative Structureではない。
- Type / Fileに実在するResponsibility / Owner / Lifetime / Boundary / Split Reasonがある。
- DRY共通化ならProven Knowledge Duplicationと同一Change Reasonが確認済みである。
- SOLID由来の抽象化なら実在するVariation / Boundary / Dependency理由がある。
- SRPをPropertyまたはMethod単位のType分割として使用していない。

Shader変更はRule ID、Confirmed Finding、または明示されたユーザー目標を根拠にする。

### Step 4 — Implement with compatibility preservation

- public/serialized契約を保持する。
- 契約変更がSpecにある場合はMigrationを同じTask契約に従って実施する。
- Runtime codeへEditor APIを混ぜない。
- RenderGraphとCompatibility APIを混在させない。
- Resourceの生成、所有、破棄を対にする。
- Root Namespaceが設定済みなら`<RootNamespace>.<FeatureName>`、Root Namespaceなしなら`<FeatureName>`を使用する。
- 既存コードを変更する場合は既存namespaceを保持する。
- `Namespace`、`RootNamespace`、`<RootNamespace>`、`CHANGE_ME`をC# namespace、asmdef名、`rootNamespace`、Assembly参照へ出力しない。
- 先頭または末尾が`.`のnamespaceを生成しない。
- コメントは`.ai/user-policy.yaml`のコメント体系に従い、日本語で意図、制約、所有権、寿命、危険箇所を必要な密度で書く。
- Type / Responsibility / File Structureを確定してから命名を評価する。長いType名を短縮するためだけに追加Typeを作らない。

新規Typeまたは明示Renameがある場合のみSemantic Type Naming Reviewを行う。

- Readabilityを短さより優先する。
- Type名が責務を正確に表す。
- Namespace / Context redundancyを避ける。
- UnityAgentが新しい略語を発明しない。
- Role suffix stackingを避ける。
- `Manager` / `Controller` / `Service` / `System`は実在責務がある場合だけ使用する。
- LengthはReview TriggerでありHard Limitではない。
- Existing Public / Serialized APIをNaming改善だけでRenameしない。

既存Typeを触るだけのLocal FixではNaming Reviewを無理に発火させない。

### Step 5 — Self-review the diff

確認項目:

- Task外のファイルを変更していない
- 不要な名前変更、移動、整形差分がない
- namespaceとasmdef名が実際のプロジェクト規約に一致する
- namespace、`rootNamespace`、Assembly参照にプレースホルダーが残っていない
- null、例外、破棄、イベント解除
- Allocation、boxing、コピー、毎フレーム探索
- Serialization、AOT、stripping
- Shader state、Queue、Pass、Keyword
- Debug codeと一時ログの残存
- 新規ファイルごとのSplit Reason
- speculative abstractionがない
- Property単位Type proliferationがない
- 1実装Interfaceを理由なく追加していない
- Pattern名だけを理由にClassを追加していない
- DRYがSyntax similarityだけを根拠にしていない
- SOLIDが機械的Layering Ruleとして使われていない
- NamingがArchitecture判断を逆方向に支配していない
- 新規/明示Rename TypeがSemantic Type Naming Contractを満たす
- Context redundancy / invented abbreviation / role suffix stackingがない
- Existing APIをNaming理由だけで変更していない
- コメントがProductionまたはLearning Profileに一致している

### Step 6 — Validate at the strongest available level

1. Static inspected
2. Local validator / unit test passed
3. Unity compilation passed
4. Editor reproduction passed
5. Player / IL2CPP passed
6. Target-device measurement passed

実施していない確認を推測で埋めない。
性能変更は対応Evidence Skillへ渡し、Before/Afterがなければ改善確定としない。

### Step 7 — Stop at the selected boundary

現在Taskが完了しても、次Taskへ自動的に進まない。
必要な追加作業はFindingまたはNext Taskとして報告する。

## Output contract

- Task / Incident / Rule ID
- Changed files
- 変更内容と理由
- 使用したnamespaceとAssembly名
- 新規ファイルのSplit Reason
- 保持または変更した互換性契約
- Engineering Principles Review when structure was added
- Semantic Type Naming Review when new or renamed Types were involved
- Spec / Planとの差異
- 実施した検証と結果
- 未検証事項
- 発見した別問題
- Revert条件

## Scope — what this Skill does not do

- 未選択Taskへ進まない。
- 原因未確定の修正を行わない。
- 依頼範囲外のアーキテクチャ刷新を行わない。
- 勝手に追加システムやDebug UIを作らない。
- 未確定のRoot Namespaceをプレースホルダーで埋めない。
- Unityコンパイル、Player、実機、性能を未実施のまま成功扱いしない。
- 一般的Best PracticeでUser Policyを上書きしない。
- SOLIDを理由に仕様外のLayer / Interface / Typeを追加しない。
- Naming Contractを理由に既存Public / Serialized Typeを勝手にRenameしない。

## Checklist

- [ ] Task / Incident / Rule IDを固定した
- [ ] `.ai/user-policy.yaml`を適用した
- [ ] Changed filesとNon-goalsを確認した
- [ ] 必要な規約だけを読んだ
- [ ] Existing OwnerとSimplest Cohesive Solutionを先に確認した
- [ ] Speculative Structureを追加していない
- [ ] Namespaceとasmdef名を既存コード、asmdef、検出済みFactから確定した
- [ ] Project Profileを使用した場合は未解決FactのFallbackとしてのみ使用した
- [ ] Namespace placeholderが残っていない
- [ ] 最小の因果変更に限定した
- [ ] 新規ファイルごとのSplit Reasonがある
- [ ] DRY / SOLID由来の抽象化に確認済みの根拠がある
- [ ] 新規/明示Rename TypeだけSemantic Namingを確認した
- [ ] public/serialized/Shader契約を確認した
- [ ] Diffを自己レビューした
- [ ] コメントProfileを確認した
- [ ] 検証状態を正確に報告した
- [ ] 次Taskへ進んでいない

## Common mistakes

- `RootNamespace: CHANGE_ME`を見て`Namespace`や`CHANGE_ME`を実名として出力する。
- 検出済みProject FactがあるのにProject Profileの固定値で上書きする。
- Root Namespaceなしのプロジェクトへ`.FeatureName`のような無効namespaceを生成する。
- asmdefの`name`だけ直し、`rootNamespace`やAssembly参照を更新しない。
- 指定Taskを終えた勢いで後続Taskも実装する。
- 小さな修正のために新しいControllerやManagerを作る。
- SRPを理由にPropertyごとのTypeを作る。
- 将来用にInterface / Base / Default implementationを先に作る。
- 見た目が似たCodeをGeneric Helperへ早期共通化する。
- 長いType名を意味不明な略語へ短縮する。
- Manager / Controller / Serviceをsuffixとして積み重ねる。
- 既存Serialized fieldやPublic TypeをNaming改善だけで改名し、互換性を壊す。
- RendererFeature修正で無関係なShader Passを追加する。
- Editorでコンパイルしていないのに「動作確認済み」と書く。
- 性能に良さそうなコード変更を、実測済み最適化として報告する。
- 古いProject Constitutionを現在のPolicyより優先する。

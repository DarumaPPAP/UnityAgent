# UnityAgent 現行挙動・思想・コード生成傾向監査

> Status: **Observation / Review Draft**  
> この文書は現行 `main` を観測して整理したレビュー資料であり、UnityAgentの新しい正本Policyではない。  
> ユーザー修正案とレビューを受けた後に、必要なPolicy・Skill・Context Routeへ反映する前提とする。

## 1. 目的

現在の `DarumaPPAP/UnityAgent` を正本としてUnity実装を行った場合に、AIがどのような思想・設計判断・命名・ファイル粒度・コメント・コード整形で出力しやすいかを可視化する。

特に次を明確にする。

- 現在のUnityAgentが強く誘導している設計思想
- 明示的に定義されている命名規則
- 明示されているファイル分割規則
- コメント規則
- 改行・インデント・波括弧・宣言順などのコードフォーマット規則
- 現行Policyの強み
- 現行Policyが迷走しやすいポイント
- 修正候補

## 2. 調査対象

主に以下を現行 `main` から確認した。

- `AGENTS.md`
- `.ai/user-policy.yaml`
- `.ai/context-index.yaml`
- `.ai/context-packs/csharp-local-fix.yaml`
- `.ai/context-packs/portable-feature.yaml`
- `.ai/task-contracts/architecture-design.yaml`
- `.agents/skills/unity-coding-standards/SKILL.md`
- `.agents/skills/production-code-comments/SKILL.md`
- `SkillReferences/CODING_STANDARDS.md`
- `SkillReferences/ARCHITECTURE_STANDARDS.md`
- `SkillReferences/ARCHITECTURE_DECISION_POLICY.md`
- `SkillReferences/JAPANESE_CODE_COMMENT_STANDARDS.md`

また、Architecture Intelligence / Single Cohesive Script Firstを導入したコミット履歴も確認した。

---

# 3. 現在のUnityAgentの基本思想

## 3.1 User Policy最優先

現在の優先順位は明確である。

1. 今回のユーザー明示指示
2. `.ai/user-policy.yaml`
3. Project固有Policy
4. Unity Domain Standard
5. 外部Reference
6. 一般的Best Practice

つまり、UnityAgentは「一般的なUnity Best Practice Agent」ではなく、**ユーザー専用Unity開発Agent**として設計されている。

これは現在のUnityAgentの最も重要な特徴である。

## 3.2 最小構成志向

小規模機能では `Single Cohesive Script First` が強く設定されている。

現在の基本思想は次の通り。

- 小規模Local Behaviorはまず1つのMonoBehaviourで成立するか確認する
- Pattern名から設計を始めない
- 将来の再利用可能性だけで分割しない
- Mock可能性だけでInterfaceを作らない
- MonoBehaviourを薄くする目的だけでPlain C#やScriptableObjectへ分割しない
- 行数だけを理由にファイル分割しない
- Controller / Manager / Serviceを形式上追加しない

この方向性そのものは、過剰設計防止としてかなり強い。

## 3.3 Ownership / Lifetime重視

設計時には以下を強く意識させる構造になっている。

- creator
- owner
- lifetime
- readers / writers
- initialization
- release / disposal
- Scene Load / Unload
- Domain Reload

つまり、単なる「動くコード」ではなく、**誰が状態やResourceを所有し、いつ生まれていつ破棄されるか**を重視する傾向がある。

## 3.4 投機的な抽象化を禁止

以下はかなり明確に抑制されている。

- speculative Controller
- speculative Manager
- speculative Service
- speculative Interface
- speculative ScriptableObject
- speculative DI
- speculative Profile
- speculative Cache
- speculative Fallback

これは現在のUnityAgentの強み。

## 3.5 Evidence重視

Static / Compile / Editor / Player / Target Device / Performance / Visualを分離して扱う。

特にPerformanceでは、

- Baseline
- Before / After
- 品質条件
- Revert条件

を要求する思想が強い。

---

# 4. 現在のArchitecture選択傾向

## 4.1 Scope分類

新規設計では以下へ分類する思想になっている。

- Local Behavior
- Feature
- System
- Project Infrastructure
- Data-parallel Simulation

### Local Behavior

基本候補:

```text
Single MonoBehaviour
```

または

```text
Primary MonoBehaviour
+ 同一ファイル内のprivate / feature-local helper
```

### Feature

必要性に応じて:

```text
MonoBehaviour
+ Plain C# Logic
+ ScriptableObject
```

ただし自動的には追加しない。

### System

複数のFeature、Scene、Resource、入力を実際に調停する場合のみController / Coordinator等を許可する。

### Data-parallel Simulation

対象数・更新頻度・同質性・並列化可能性がある場合は、ECS / Jobs / Burstを積極候補にする。

---

# 5. ファイル分割規則

## 5.1 1 File 1 Primary Unity Type

Unity上で独立してアタッチ・生成・参照される以下は原則1ファイル1Primary Type。

- MonoBehaviour
- ScriptableObject
- EditorWindow
- CustomEditor
- ScriptedImporter
- RendererFeature

## 5.2 同一ファイルに残しやすいもの

以下は機械的に別ファイル化しない。

- private enum
- private class
- private readonly struct
- Feature-local Result
- Feature-local Comparer
- Feature-local Job
- ECS Component
- ECS Tag
- ECS Aspect
- System専用Job
- RenderGraph PassData
- 小規模内部State

## 5.3 新規ファイルに必要なSplit Reason

新規C#ファイルには実在する分離理由を要求する。

例:

- 独立してアタッチされるMonoBehaviour
- 独立Asset Identityを持つScriptableObject
- Runtime / Editor境界
- Managed / Burst境界
- ownerが異なる
- lifetimeが異なる
- Assembly依存が異なる
- Package依存が異なる
- 複数Featureから実際に共有される
- 外部Systemとの独立契約
- 単独置換するBackend

## 5.4 現在の傾向

**ファイルを作りすぎる問題への抑制はかなり強い。**

一方で、後述する通り `Single Cohesive Script First` が強いため、適用を誤ると「別ComponentのUnity Lifecycleを利用した方が自然なのに、1Componentから監視して完結させる」という逆方向の不自然さを生む可能性がある。

---

# 6. 命名規則

`SkillReferences/CODING_STANDARDS.md` と `AGENTS.md` で明示されているもの。

| 対象 | 現行規則 | 例 |
|---|---|---|
| public type | PascalCase | `CameraAntiAliasingSwitcher` |
| public API/member | PascalCase | `ApplySettings()` |
| private field | `_camelCase` | `_cameraData` |
| const | `SCREAMING_SNAKE_CASE` | `MAX_SAMPLE_COUNT` |
| enum type | `E_UPPER_SNAKE_CASE` | `E_MSAA_SAMPLE_COUNT` |
| struct type | `S_UPPER_SNAKE_CASE` | `S_RENDER_STATE` |
| namespace | ProjectのRoot Namespaceを解決して決定 | `Game.Rendering` 等 |

## 6.1 Namespace

現在のルールは比較的厳格。

- 既存コード修正では既存namespaceを維持
- asmdefの`rootNamespace`があるなら `<RootNamespace>.<FeatureName>`
- Root NamespaceがなければFeature名のみ
- 不明な場合に `RootNamespace` や `CHANGE_ME` を実名として出力しない

これは良い。

## 6.2 Controller / Manager / Serviceという名前

名前そのものは禁止ではない。

ただし、以下を実際に所有しないなら作らない。

- 複数参加要素の調停
- 実行順序
- 状態遷移
- Resource生成/破棄
- Scene跨ぎLifetime
- Failure / Retry / Cancellation

つまり `Manager` という単語を避けるのではなく、**責務のないManagerを避ける**思想。

---

# 7. コメント規則

コメントPolicyはかなり完成度が高い。

## 7.1 Production Comment

基本は日本語。

優先して説明するもの:

- 理由
- 制約
- 意図
- 副作用
- 破綻条件
- 所有権
- Lifetime
- 実行順
- 実機差
- 性能意図

禁止傾向:

```csharp
// nullならreturn
if (_material == null)
{
    return;
}
```

のようなコードの復唱。

## 7.2 コメント密度

ProductionではLevel 1〜2を基本とし、通常1〜3行。

Learning用途だけ、SDS / CRF / 代替案 / アナロジーを増やす。

このProduction / Learning分離は現状かなり良い。

---

# 8. 改行・インデント・コード整形規則

## 8.1 現状の最大の空白領域

**現行UnityAgentには、C#の最終的な見た目を固定するFormatting Standardがほぼ存在しない。**

調査した範囲では、以下を正本として明示する規則を確認できなかった。

- TabかSpaceか
- インデント幅
- Allman / K&R等の波括弧Style
- 1行最大文字数
- メソッド引数を何文字で改行するか
- メソッドチェーンの改行方式
- 二項演算子の前後どちらで改行するか
- `if` 条件の複数行整形
- 属性の配置
- `[SerializeField]` とfieldを同じ行にするか
- field宣言の空行ルール
- `using` の並び順
- member declaration order
- expression-bodied memberを許可するか
- `var` の使用方針
- explicit typeの使用方針
- 1行`if`でbraceを省略してよいか

さらにRepository rootには、調査時点でC#用 `.editorconfig` も確認できなかった。

## 8.2 現在何が起きるか

そのため、現在のUnityAgentを正本にしても、最終コードの改行は以下に依存しやすい。

- 使用しているモデルの既定Style
- 直前の会話中コードStyle
- 参照したSourceの局所Style
- Exampleコードの見た目

つまり、**設計ルールは強いが、コードの見た目は決定論的ではない。**

## 8.3 Allman Styleについて

Reference内のExampleは次のようなAllman風が多い。

```csharp
if (_material == null)
{
    return;
}
```

しかしこれは現状「正本Formatting Rule」として明文化されているわけではない。

よって、現時点では

> Allman Styleになる傾向はあるが保証されない

が正確。

---

# 9. Member Declaration Order

現行正本には、C#クラス内の宣言順を固定する明確な規則を確認できなかった。

例えば以下の順序は現在保証されない。

```text
const
static
[SerializeField]
public field/property
private field
event
Unity Lifecycle
public method
private method
```

この項目は、ユーザーがコードの読みやすさを強く意識する場合、専用Formatting Standardとして明文化した方がよい。

---

# 10. Unity Lifecycleの扱い

ここは今回のMainCamera AA切替のやり取りで問題が顕在化した。

現行PolicyにはOwnership / Lifetimeを重視する規則はあるが、次のような**Unity Native Lifecycle First**規則は明示されていない。

```text
状態変化がOnEnable / OnDisable / Awake / Start / OnDestroy等で表現できる場合、
Update pollingや追加状態監視より先にLifecycle Callbackで解決できないか確認する。
```

そのため、AIが「状態を追跡する必要がある」と判断すると、次のような余計なものを作る余地がある。

- `_previousState`
- `Update()` polling
- 監視対象`GameObject`
- Refresh method
- force flag
- 追加Serialized reference

今回の要件では、MainCameraにのみComponentを付けるなら、MainCamera自身の `OnEnable / OnDisable` で完結できるため、上記は不要だった。

これは現在のUnityAgentで追加した方がよい重要Rule候補。

---

# 11. 現在のRequirement解釈傾向

`.ai/user-policy.yaml` には `no_unrequested_implementation` が存在する。

しかし実運用では、Architecture Skillが以下を強く考えるため、要求の外側へ思考が膨らむ余地がある。

- owner
- lifetime
- participants
- change axis
- architecture candidate
- split reason
- validation

これ自体は悪くない。

問題は、**Local BehaviorレベルでもArchitectureの検討量が大きくなりすぎる可能性**がある点。

特に今回のような依頼:

```text
MainCameraに付けるComponent
Activeになったら設定変更
InactiveになったらDefaultへ戻す
```

は、本来まず次の4点だけで十分。

1. どのGameObjectに付くか
2. どのLifecycleで状態が変わるか
3. 何を変更するか
4. 何を復元するか

ここでArchitecture Candidate比較まで広げる必要はない。

---

# 12. 現在のUnityAgentから出やすいコードの傾向

## 強く出やすい傾向

- private fieldは`_camelCase`
- public型/memberはPascalCase
- feature-local enumは同一ファイル
- 小規模機能は1MonoBehaviourを優先
- 不要Interfaceを避ける
- 不要Managerを避ける
- ScriptableObject乱用を避ける
- public / Serialized契約を壊さない
- ownership / lifetimeをコメントしやすい
- Productionコメントは日本語
- null guardを比較的入れやすい
- Performance主張は測定を要求しやすい

## 揺れやすい傾向

- 改行位置
- 1行の長さ
- field/memberの宣言順
- `var` / explicit type
- brace styleの厳密性
- 属性配置
- Inspector用Tooltipの量
- null guardの過不足
- `Update` vs Lifecycle Callbackの選択
- SerializedFieldを追加する判断
- Local BehaviorにどこまでArchitecture検討を持ち込むか

---

# 13. 現行UnityAgentの強み

## 13.1 過剰設計防止

かなり強い。

特に

- Interface乱造
- Service乱造
- ScriptableObject乱造
- 1型1ファイル乱造
- MVP/MVVMの機械適用

への抑制は有効。

## 13.2 Project固有事実とUser Policyの分離

これも良い。

ユーザーPreferenceを一般論で上書きしない思想が明確。

## 13.3 Rendering / PerformanceのEvidence思想

Editorで動いたからPlayerもOK、CompileしたからRuntimeもOK、という誤判定を避ける方向に強い。

## 13.4 コメントPolicy

ProductionとLearningを分離している点は優秀。

---

# 14. 現行UnityAgentの問題・迷走ポイント

以下は今回の監査から見た修正候補。

## P0-1. Code Formatting Standardがない

最優先。

現在は命名だけ固定して、最終コードStyleが固定されていない。

追加候補:

```text
SkillReferences/CODE_FORMATTING_STANDARDS.md
```

ここで最低限以下を正本化する。

- Tab / Space
- indentation
- brace style
- member order
- line wrapping
- parameter wrapping
- condition wrapping
- using order
- attribute placement
- blank line policy
- `var` policy
- expression-bodied policy

さらに可能なら `.editorconfig` も用意し、文章Policyだけでなく機械的に検証できるようにする。

## P0-2. Unity Native Lifecycle Firstを追加

候補Rule:

```text
Unity Lifecycle Callbackで要求された状態遷移を直接表現できる場合、
Update polling、前回状態キャッシュ、監視専用field、追加GameObject referenceを導入しない。
```

優先順位例:

```text
Direct API / Lifecycle callback
↓
Existing Event / Callback
↓
Explicit Event
↓
Polling
```

Pollingは最後の手段とする。

## P0-3. Requirement Surface Lockを追加

AIがユーザー要求に存在しないObject・Reference・Manager等を勝手に増やす問題への対策。

候補Rule:

```text
実装前に、ユーザーが明示したComponent / GameObject / Asset / Input / OutputをRequirement Surfaceとして固定する。
新しいSerialized reference、GameObject、Asset、Manager、Profile、監視対象を追加する場合、要求達成に不可欠な理由が必要。
```

今回ならRequirement Surfaceは:

```text
MainCamera
Camera Component
UniversalAdditionalCameraData
URP Asset
OnEnable
OnDisable
```

で終わる。

`Target Object` はSurface外なので原則追加禁止になる。

## P0-4. Local Behavior Fast Pathを追加

`architecture-design` がLocal Behaviorまで重くしすぎないようにする。

例えばLocal Behavior判定時は次だけ確認する。

1. Attach先
2. Unity Lifecycle
3. Local state / resource
4. Serialized input
5. Side effect / restore

これだけで成立するならArchitecture Candidate比較を省略する。

## P0-5. No Extra State Rule

候補:

```text
既存のUnity状態そのものがSource of Truthなら、同じ状態を表すboolやprevious-state cacheを追加しない。
```

今回なら `gameObject.activeInHierarchy` を追跡する `_previousTargetActive` は不要。

さらにMainCamera自身のActiveがTriggerなら `activeInHierarchy` の監視自体も不要。

---

# 15. P1修正候補

## P1-1. SerializedField追加基準

現在はScriptableObjectの追加基準は強いが、`[SerializeField]` そのものを増やす基準は弱い。

候補:

```text
SerializedFieldはAuthoring時に変更する必要がある値・参照だけにする。
Runtimeで自身から確定取得できるComponentをInspector参照にしない。
```

例:

```csharp
Camera camera = GetComponent<Camera>();
```

で確定できるならCamera自体を`[SerializeField]`しない。

## P1-2. Built-in Unity Mechanism First

Lifecycleだけでなく、Unity標準の機構をCustom状態管理より優先する。

例:

- `OnEnable / OnDisable`
- `OnDestroy`
- `OnValidate`
- `RequireComponent`
- `TryGetComponent`
- `IPointer...`
- Animator StateMachineBehaviour
- Timeline notification
- UnityEvent / C# event（既存契約がある場合）

ただし「何でもUnityEventにする」という意味ではない。

## P1-3. Small Code Comment Budget

Ownership / Lifetimeを意識しすぎて、小規模Scriptでもコメントが重くなる場合がある。

Local Behaviorでは:

- class summary 0〜1個
- 非自明なrisk/side effect 0〜2個

程度を基本にしてもよい。

## P1-4. Architecture Output Contractのスケーリング

現在のArchitecture Decisionは最大16項目あり、小規模作業では過剰。

ScopeごとにOutputを変える方がよい。

### Local Behavior

```text
Goal
Lifecycle
State / Side Effects
Implementation
Validation
```

### Feature / System

現在の詳細Architecture Decisionを使用。

---

# 16. P2修正候補

## P2-1. Evalに「余計な実装をしない」テストを追加

今回のMainCameraケースをRegression Testに使える。

### Input

```text
MainCameraに付けるComponent。
CameraがActiveになったらAAとURP MSAAを変更し、Inactiveなら元に戻す。
```

### Expected

必須:

- MainCameraのComponentのみ
- Awakeまたは初期化でDefault保存
- OnEnableで変更
- OnDisableで復元

禁止:

- Update
- Target GameObject
- previous state cache
- polling
- Manager
- Service
- ScriptableObject
- extra Component

このようなEvalを追加すると、UnityAgentの「余計なものを作らない」が実際に検証可能になる。

## P2-2. Formatting Eval

同じ仕様を複数回生成して、以下が一致するか確認する。

- indent
- line wrap
- declaration order
- braces
- attribute layout

文章Policyだけでなく、Snapshot形式で評価する価値がある。

---

# 17. 命名規則で再検討してもよい項目

これは「変更すべき」と断定しない。ユーザー判断項目。

## enum type

現在:

```csharp
private enum E_MSAA_SAMPLE_COUNT
```

一般的なC#では

```csharp
private enum MsaaSampleCount
```

の方が多い。

ただしUnityAgentはユーザー専用なので、ユーザーが `E_UPPER_SNAKE_CASE` を読みやすいと考えるなら現状維持でよい。

同様にstructの `S_UPPER_SNAKE_CASE` もユーザー判断。

重要なのは、一般論へ合わせることではなく**ユーザーが読みやすい規則として確定しているか**。

---

# 18. ユーザー側で決めるとUnityAgentが安定する項目

次を一度確定すると、コード出力の揺れがかなり減る。

## Formatting

- Tab or Space
- Tab幅 / indent幅
- Allman or K&R
- 最大行長
- long method callの改行
- long `if` conditionの改行
- LINQ / method chainの改行

## Declaration Order

例:

```text
const
static readonly
static
[SerializeField]
public property / field
private field
event
Unity Lifecycle
public method
protected method
private method
nested type
```

## Type Style

- enum type naming
- struct type naming
- interface prefix `I`
- bool prefix `is/has/can/should`

## C# Syntax Preference

- `var`の範囲
- target-typed `new()`
- expression-bodied member
- switch expression
- pattern matching
- file-scoped namespace
- nullable reference types

## Unity Preference

- `GetComponent` vs Serialized reference
- `TryGetComponent`基準
- `Awake` / `OnEnable` / `Start`使い分け
- `Update`許可条件
- Coroutine / Task / Awaitable使い分け
- Inspector Tooltip / Header使用量

---

# 19. 現時点の評価

## Architecture思想

**強い。**

特に過剰設計防止とOwnership / Lifetimeは有効。

## File Granularity

**強い。**

過剰な1型1ファイル化を止められる。

## Naming

**かなり明確。**

ただしenum / struct規則はユーザー再確認余地あり。

## Comments

**かなり強い。**

Production / Learning分離も良い。

## Formatting

**弱い。**

現状の最大の欠落。

## Unity-native implementation selection

**弱い。**

Lifecycle / callback / built-in mechanismを最優先するRuleが不足している。

## Requirement literalness

**Policy上は禁止しているが、実運用ではまだ弱い。**

`no_unrequested_implementation` を、実装前のRequirement Surface LockやEvalで補強する価値が高い。

---

# 20. 修正優先順位案

```text
P0
├─ CODE_FORMATTING_STANDARDS.md追加
├─ Requirement Surface Lock
├─ Unity Native Lifecycle First
├─ Local Behavior Fast Path
└─ No Extra State Rule

P1
├─ SerializedField追加基準
├─ Built-in Unity Mechanism First
├─ Small Code Comment Budget
└─ Architecture Output ContractのScope別縮小

P2
├─ Overengineering Regression Eval
├─ Lifecycle Regression Eval
└─ Formatting Snapshot Eval
```

---

# 21. 今回のMainCamera AA切替を基準ケースにした理想判断

要件:

```text
MainCameraにだけComponentを付ける。
Active時にCamera AA / URP MSAAを変更する。
Inactive時にDefaultへ戻す。
```

理想判断:

```text
Attach先 = MainCamera
↓
Active / Inactive = GameObject Lifecycle
↓
OnEnable / OnDisableで直接表現可能
↓
Polling不要
↓
Target Object不要
↓
previous state不要
↓
追加Component不要
↓
1 MonoBehaviourで完結
```

この判断をUnityAgentが毎回安定して行える状態が、Local Behaviorの一つのGoalになる。

---

# 22. 結論

現在のUnityAgentは、

> **過剰設計を避け、Ownership / Lifetime / Evidenceを重視するUnity開発Agent**

としてかなり明確な思想を持っている。

一方で、現在の弱点は次の3つに集約できる。

1. **コードFormattingが正本化されていない**
2. **Unity Lifecycle / built-in mechanismをCustom状態管理より優先するRuleが不足している**
3. **Local BehaviorでもArchitecture思考が膨らみ、要求外の状態・参照を発明する余地がある**

この3点を直すと、現在の「過剰設計防止」という長所を残しながら、より短く、自然で、Unityらしいコードを安定して生成できる可能性が高い。

# Unity C# Coding Standards

## Context first

Before review or implementation, resolve Unity version, render pipeline, target platform, Editor/Player, Mono/IL2CPP, Development/Release, Burst/Jobs/Entities, hot-path frequency, public API and serialization compatibility.

Project Factは、対象Projectから直接検出した値、今回ユーザーが確認した値、Project固有Contextの順に優先する。`docs/architecture/specifications/ProjectProfile.md`は必要Factが未解決の場合だけ使用するFallbackであり、検出済みFactを上書きしない。

Local Behaviorでは、System級のArchitecture分析へ進む前にUnity Lifecycle、既存Component、既存Callbackだけで要求を満たせるかを確認する。

## Naming

Namingは **Class / Function / Variable** の3区分で適用する。いずれも **Minimum Sufficient Name**（宣言位置と利用側のContextで責務を識別できる、必要十分に簡潔な名前）を既定とする。短さだけで意味を欠落させず、冗長さを明確さと混同しない。

- Namespace、所属Class、引数型、Directory等から明らかな情報は、識別に必要な場合を除き名前に繰り返さない。
- 名前の長さや単語数だけで機械的に切り詰めない。曖昧な略語を発明せず、必要な区別は残す。
- 新規命名・明示的Renameに適用する。既存Public API、Serialized field、Prefab / Scene / Save Data、Reflection / string binding、Unity Callback、外部Interface・Libraryの契約は命名改善だけで変更しない。
- Formatting改善を理由に既存のenum / struct / field / constのcase conventionを変更しない。

### Class

Class、Struct、Interface、Enum、Unity Component、Editor拡張等の**Type名**と、そのTypeを所有する**C#ファイル名**を扱う。新規TypeやLayerの必要性を命名都合から逆算しない。

- Class / Interface / 通常のType名は`PascalCase`。enum typeは`E_UPPER_SNAKE_CASE`、struct typeは`S_UPPER_SNAKE_CASE`を維持する。**新規の独自TypeはClassを既定**とし、Struct / readonly structは後述の採用条件を満たす場合に限る。採用が決まったStructについて、値の不変性が必要なら`readonly struct`を検討する。
- Type / Responsibility / File Structureを先に確定する。既存Ownerで実現できる場合、新規Typeを増やさない。
- Subjectと主要Roleを必要な範囲で表し、`Manager` / `Controller` / `Service` / `System`等のSuffixを積み重ねない。実際に所有する責務がなければRoleを付けない。
- Namespace、既存のFeature名、Directory名のContextを無条件に繰り返さない。一方、Typeの利用箇所で区別が必要なSubjectは残す。
- 新規C#ファイルには実在するSplit Reasonを要求する。UnityのPrimary Typeを持つファイルは原則そのType名と一致する`<TypeName>.cs`とし、File名に別の説明語を付加しない。複数補助Typeを含むファイルはPrimary Type / 実際の責務で命名する。
- 長さ（33文字以上等）はReview Triggerであり、短縮・Failを文字数だけで決めない。冗長な修飾語はまず削除を検討する。

| 冗長な例 | 必要十分な候補 | 条件 |
| --- | --- | --- |
| `PlayerHealthValueManagementController` | `PlayerHealth` | PlayerのHealth状態を所有するType |
| `ShaderVariantCollectionAnalysisManager` | `ShaderVariantAnalyzer` | Shader Variantの分析が責務 |
| `CameraDebuggingCameraStateTracker` | `CameraStateTracker` | `CameraDebugging` namespace内 |
| `PlayerHealthValueManagementController.cs` | `PlayerHealth.cs` | Primary Typeを`PlayerHealth`へ新規設計する場合 |

Semantic Type Namingの詳細正本は`docs/standards/TYPE_NAMING_STANDARDS.md`。新規Type、Architecture ProposalのPlanned Type、明示的Renameに適用する。既存Typeを触るだけのLocal Fixには無条件にNaming Reviewを発火させない。

#### Namespace resolution

Namespaceは実装前に、次の優先順位で確定する。

1. 変更対象の既存コードで使用中のnamespace
2. 対象Projectから検出したasmdefの`rootNamespace`と既存Assembly契約
3. 今回ユーザーが確認したProject固有Fact
4. 上記で必要なFactが未解決の場合だけ`docs/architecture/specifications/ProjectProfile.md`

`docs/architecture/specifications/ProjectProfile.md`のテンプレート値や固定値を、検出済みProject Factより優先してはならない。

- `RootNamespace`が設定済みの場合: `<RootNamespace>.<FeatureName>`
- プロジェクトがRoot Namespaceを使用しない場合: `<FeatureName>`
- 既存機能を変更する場合: 既存namespaceを保持する

次を実際のC# namespace、asmdef名、`rootNamespace`、Assembly参照へ出力してはならない。

- `Namespace`
- `RootNamespace`
- `<RootNamespace>`
- `CHANGE_ME`
- 先頭または末尾が`.`のnamespace

Root Namespaceが未設定または不明な場合、プレースホルダーを実名として補完しない。既存プロジェクト規約を確認するか、Root Namespaceなしの運用が明示されている場合はFeature名だけを使用する。

#### Semantic type review

新規Typeまたは明示Renameでは次を確認する。

- Type NecessityがArchitectureで先に確認されている。
- 名前が責務を正確に表し、所属Contextで識別できる必要十分な長さである。
- Namespace / Directory / Contextの不要な重複、invented abbreviation、Role suffix stackingがない。
- Property単位Type proliferationではない。
- `Manager` / `Controller` / `Service` / `System`に実在責務がある。
- 文字数だけをHard Fail、または意味を壊す短縮理由にしていない。
- Existing Public / Serialized APIをNaming改善だけで変更していない。

### Function

Method / Local Function（public、private、protected、internal）を扱う。

- `PascalCase`とし、関数名のどの位置にも`_`を使用しない（`_UpdateTarget`、`Update_Target`、`UpdateTarget_`は禁止）。
- **動詞＋必要な対象**を基本とする。Boolを返す判定は`Is...` / `Has...` / `Can...`等、結果と動作を正確に表す名前を優先する。
- 所属Classの責務から分かるSubjectや`Current`、`Value`、`Data`、`Processing`等の説明語は、区別に必要でなければ追加しない。
- private MethodはClassのContextを活用する。public Methodは呼び出し側から読んでも誤解しない必要な対象を残す。
- `Get`、`Calculate`、`Restore`、`Save`等は実際の処理に合わせる。短縮によって取得と計算、既定値への初期化と以前の値への復元等を混同しない。

| 所属Class | 冗長な例 | 必要十分な候補 |
| --- | --- | --- |
| `CameraAAOverride` | `RestorePreviouslySavedCameraAntiAliasingSettings()` | `RestoreOriginalSettings()` |
| `ShaderVariantAnalyzer` | `GenerateShaderVariantAnalysisReport()` | `GenerateReport()` |
| `PlayerHealth` | `CalculateCurrentPlayerHealthPercentage()` | `CalculateHealthRatio()` |

`Awake`、`OnEnable`、Interface実装、Override等の契約上固定されたMethod名は維持する。名前を短くするために振る舞い・公開契約を変更しない。

### Variable

Field / Property / Parameter / Local Variable / Constを扱う。宣言位置と使用範囲を踏まえ、値の意味・単位・区別に必要な語だけ残す。

- private field: `_camelCase`（`_health`、`_originalSettings`）。`_` prefixはField用でありFunction名に流用しない。
- public property / public member: `PascalCase`。
- parameter / local variable: `camelCase`（`camera`、`index`、`maxHealth`）。
- const: `SCREAMING_SNAKE_CASE`。
- 同じClass・Scopeに複数の候補があるときは`Original` / `Current` / `Target`、単位、用途等で必要な区別を残す。語句を省くために別の意味へ変えない。
- Data Class / ScriptableObject等では、`No` / `Count` / `Value`など用途が分からない名前を避け、`Number` / `CutCount`等の対象と意味を識別できる語を使う。既存のPublic / Serialized APIの改名は互換性レビューなしで行わない。

境界・範囲を表す名前は包含・排他条件と一致させる。

- `min` / `max`: **両方の限界値を含む**下限・上限。例: `minValue <= value && value <= maxValue`。
- `first` / `last`: **先頭・末尾の要素をともに含む**範囲。例: `firstIndex`から`lastIndex`まで。
- `begin` / `end`: **始点を含み、終点を含まない**半開区間 `[begin, end)`。例: `beginIndex <= index && index < endIndex`。空範囲は`beginIndex == endIndex`で表せる。

```csharp
private bool IsWithinLimits(int value, int minValue, int maxValue)
{
	return value >= minValue && value <= maxValue;
}

private void VisitInclusiveRange(int firstIndex, int lastIndex)
{
	for (int index = firstIndex; index <= lastIndex; index++)
	{
		Visit(index);
	}
}

private void VisitHalfOpenRange(int beginIndex, int endIndex)
{
	for (int index = beginIndex; index < endIndex; index++)
	{
		Visit(index);
	}
}
```

#### Data member documentation

新規または明示的に修正するData Class、Serializableな設定型、ScriptableObject、DTO等の**データ保持を主目的とするType**では、各Field・Property（Serialized / Public / Privateを含む）に、値が**何を指すか**分かる日本語のコメントを付ける。名前の機械的な言い換えではなく、対象・意味・単位・値域・null許容・対応する外部データの列など、必要な情報を簡潔に記載する。Constructor ParameterはField / Propertyとの対応が曖昧な場合に`<param>`等で補足する。

Inspector公開値には必要に応じて`[Tooltip]`を併用する。XML `summary`は公開APIの意味説明に使い、コメントを変更するためだけにSerialized Memberや既存Propertyを改名しない。

```csharp
[Serializable]
public sealed class CameraCut
{
	/// <summary>カメラワーク一覧における識別番号。</summary>
	[SerializeField] private int _number;

	/// <summary>撮影動作の組み合わせを記した説明文。</summary>
	[SerializeField] private string _description;

	/// <summary>元データで、この構成が使用されたカット数。</summary>
	[SerializeField] private int _cutCount;

	/// <summary>順番に再生する各カメラワーク段階。</summary>
	[SerializeField] private CameraPhase[] _phases;

	/// <summary>カメラワーク一覧における識別番号。</summary>
	public int Number => _number;

	/// <summary>元データで、この構成が使用されたカット数。</summary>
	public int CutCount => _cutCount;
}
```

Data型以外のすべてのLocal Variableや通常処理にまで説明コメントを拡大しない。詳細なコメントの書き分けは`docs/standards/JAPANESE_CODE_COMMENT_STANDARDS.md`を参照する。

## Formatting

C#の改行、代入、Method Call、条件、引数、brace、indentation、member orderは`docs/standards/CODE_FORMATTING_STANDARDS.md`を正本とする。

特に次を守る。

- 1行で自然に読める代入、関数宣言、関数呼び出し、条件式、三項演算子、Method Chain、LINQ式は1行を優先する。
- 行長や引数数だけを理由に機械的に改行しない。
- `=`の直後で機械的に改行しない。
- `&&`、`||`、`?`、`:`を単なる改行境界として使用しない。
- 短いMethod CallやProperty accessを縦へ分解しない。
- 式そのものが複雑な場合は、意味のある中間結果への分離を検討する。
- 条件分離では短絡評価、評価順序、評価回数、副作用、実行コスト、後続処理を維持する。
- 既存コードの改行をFormatterの好みだけで変更しない。

```csharp
_cameraData = camera.GetUniversalAdditionalCameraData();
_defaultAntiAliasing = _cameraData.antialiasing;
```

## Design

新規Type / Interface / Layer / Fileを追加する前に`docs/standards/ENGINEERING_DESIGN_PRINCIPLES.md`を適用する。

- KISS → YAGNI → Cohesion / SRP → Proven DRY → Conditional SOLIDの順で判断する。
- Prefer explicit ownership and lifetime, but do not invent ownership state that the requested local behavior does not need.
- Use Minimum Cohesive Solution First for local behavior and small features.
- DRYは見た目の重複ではなく、同一Knowledge / Change Reasonの実在する重複にのみ適用する。
- SRPをProperty単位のClass分割として扱わない。
- OCP / LSP / ISP / DIPは実在するVariation、Inheritance / Interface、Boundary、Dependency理由がある場合だけ適用する。
- Architecture Patternは問題適合性が確認された場合だけ使用する。
- ユーザーが指定したGameObject、Component、Asset、対象範囲をRequirement Surfaceとして保持し、再利用性だけを理由に任意Target化しない。
- Unity Lifecycleまたは既存Callbackで解決できる場合、独自Event、Coroutine、Timer、`Update` Pollingより先に採用する。
- Unity APIまたは既存Domain ObjectがSource of Truthを持つ状態を、理由なくprivate fieldへ複製しない。
- Unity上で独立してアタッチ、生成、参照されるMonoBehaviour、ScriptableObject、EditorWindow等は原則1 File 1 Primary Unity Typeとする。
- private補助型、Feature専用Enum、Result、Comparer、Job、ECS Component、Tag、Aspect、System専用型を無条件に別ファイルへ分離しない。
- 新規C#ファイルにはowner、lifetime、execution boundary、confirmed reuseまたはindependent contractのSplit Reasonを要求する。
- hypothetical reuse、Pattern適合、Mock可能性、行数だけを分離理由にしない。
- Do not add mutable static state, static events, Singleton or Service Locator.
- Do not create `Manager`, `Controller`, `Util`, `Common`, `Helper` without a precise responsibility.
- Controller、Manager、Serviceは状態、順序、Lifetime、Resource、複数参加要素の調停を所有しない場合は作成しない。
- Do not add Profile/Controller/Platform abstraction unless the specification requires it.
- 1実装しかないInterfaceは、外部境界または実在するVariation Axisがなければ作成しない。
- ScriptableObjectは独立したAsset Identity、共有、差し替え、Authoring要件がある場合だけ作成する。
- Do not change public API, serialized names/types, enum values, save formats or file names without compatibility analysis.
- 詳細なArchitecture判断では`ARCHITECTURE_DECISION_POLICY.md`を使用する。

### Class-first / Static and Struct restrictions

**独自のClass / static / Structについての新規設計規則**とし、Unity / .NETの既存値型（`Vector3`、`Color`等）や既存の契約を変更対象としない。

- **Class first**: 新規の通常Dataモデル、状態・責務を持つ型は`class`を原則とする。コード行数、allocationへの根拠のない恐れ、"軽そう"という印象だけで`struct`にしない。
- **Struct / readonly struct**: 値としての同一性・コピー・サイズ・不変性・boxing・default値・性能等に関する実在要件がある場合だけ採用する。ECS / Jobs / Burstなど、unmanaged value typeが必要な実行基盤は例外となる。採用理由を実装またはPRで説明する。`readonly struct`をClass代わりの定型Data Containerとして生成しない。
- **static class / static Method**: 所有者・Lifetimeを持つInstance設計を優先する。Unity / .NET API契約上staticが必須の場合、またはInstance状態を一切持たない純粋な演算・共有定数などstaticを採用する具体的な理由がある場合のみ許可する。Methodをstaticにすれば性能が良いという推測は採用理由にならない。
- **static mutable state / Event**: 原則追加しない。必要性が確定した場合はOwner、初期化・破棄・Reset、Domain Reload無効時の振る舞い、テスト隔離を明示する。Singleton / Service Locatorの安易な導入は禁止する。
- **例外の最小化**: 既存のUnity Callback / `[MenuItem]` / Extension Method / Generic制約 / 他ライブラリの契約等は壊さない。単にClassにすると無意味なInstanceが増えるだけの純粋関数は、責務を明示した上で例外判断する。
- この規則は既存ソースの一律変換やPerformance最適化を指示しない。明示的なRefactorの依頼がない場合、互換性を優先する。

根拠: [Microsoft Class / Struct選択](https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/choosing-between-class-and-struct)、[Microsoft static class](https://learn.microsoft.com/en-us/dotnet/csharp/programming-guide/classes-and-structs/static-classes-and-static-class-members)、[Unity Domain Reload](https://docs.unity3d.com/ja/current/Manual/domain-reloading.html)、[Unity MenuItem](https://docs.unity3d.com/ja/6000.0/ScriptReference/MenuItem.html)。

## Local Behavior fast path

一つのGameObjectまたはComponent内で完結する処理は、まず次の順で確認する。

1. 指定されたAttach先と責務だけで成立するか。
2. `Awake`、`OnEnable`、`Start`、`OnDisable`、`OnDestroy`等のLifecycleで成立するか。
3. 既存Component / Unity APIが必要な状態をすでに保持していないか。
4. 新しいSerialized reference、状態Cache、Watcher、Triggerが本当に必要か。
5. `Update`またはPollingを使わずに成立するか。

成立する場合、System級の候補Architecture比較、不要な汎用化、追加ファイル作成へ進まない。

## ECS, Jobs and Burst

- データ並列処理ではECS、Jobs、Burst案を評価対象から除外しない。
- ECS Component、Tag、Aspect、Jobを1型1ファイルへ機械的に分割しない。
- Feature、Query、System Group、Package依存、Public Contractを分離単位にする。
- ECS採用前にmanaged reference、structural change、sync point、Archetype、Chunk、Baking、GameObject Bridgeを確認する。
- Production性能採用にはBaseline、Before/After、品質条件、Revert条件を要求する。

## Runtime safety

- Do not add public `async void` except event or Unity callbacks.
- Do not use `Task.Result`, `.Wait()` or `.GetAwaiter().GetResult()` as normal flow.
- Use `throw;`, not `throw ex;`.
- Do not swallow exceptions or use exceptions as ordinary control flow.
- `BinaryFormatter` is prohibited.
- Reflection, `dynamic`, `Activator`, `MethodInfo.Invoke` and runtime generic construction require IL2CPP/AOT/stripping review.

## Performance

- Do not declare a pattern slow without frequency and evidence.
- In hot paths, review LINQ, closures, arrays, collections, strings, boxing, `params object[]`, logging, repeated enumeration and `Renderer.material`.
- New custom structs are opt-in rather than the default. If a value type is justified, evaluate identity, copy semantics, size, immutability, default validity, boxing and defensive copies; do not claim that structs are universally slow.
- For Burst/Jobs, require unmanaged/blittable data and explicit NativeContainer ownership/dependency completion.
- Editor success is not Player/IL2CPP proof.

## Shader boundary

ShaderLab/HLSL/Compute/RendererFeature/RenderGraph work must use `docs/standards/SHADER_PERFORMANCE_STANDARDS.md` and the dedicated Shader Agents. C# rules cover script-side property IDs, keywords, pass/kernel names, buffers and material contracts, but do not replace GPU performance analysis.

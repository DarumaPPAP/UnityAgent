# Unity C# Coding Standards

## Context first

Before review or implementation, resolve Unity version, render pipeline, target platform, Editor/Player, Mono/IL2CPP, Development/Release, Burst/Jobs/Entities, hot-path frequency, public API and serialization compatibility.

Local Behaviorでは、System級のArchitecture分析へ進む前にUnity Lifecycle、既存Component、既存Callbackだけで要求を満たせるかを確認する。

## Naming

### Namespace resolution

Namespaceは実装前に、対象プロジェクトの既存コード、asmdefの`rootNamespace`、または`Specs/ProjectProfile.md`から確定する。

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

### Other names

現行UnityAgentの命名規則を維持する。

- private field: `_camelCase`
- public API/type/member: `PascalCase`
- enum type: `E_UPPER_SNAKE_CASE`
- struct type: `S_UPPER_SNAKE_CASE`
- const: `SCREAMING_SNAKE_CASE`
- custom struct: prefer `readonly struct` when semantics allow

Formatting改善を理由にこれらの命名規則を変更しない。

## Formatting

C#の改行、代入、Method Call、条件、引数、brace、indentation、member orderは`SkillReferences/CODE_FORMATTING_STANDARDS.md`を正本とする。

特に次を守る。

- 1行で自然に読める代入は1行にする。
- `=`の直後で機械的に改行しない。
- 短いMethod CallやProperty accessを縦へ分解しない。
- 改行は意味の分離または可読性が必要な場合だけ行う。

```csharp
_cameraData = camera.GetUniversalAdditionalCameraData();
_defaultAntiAliasing = _cameraData.antialiasing;
```

## Design

- Prefer explicit ownership and lifetime, but do not invent ownership state that the requested local behavior does not need.
- Use Minimum Cohesive Solution First for local behavior and small features.
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
- Do not state that structs are generally bad. Evaluate identity, copy semantics, size, immutability, default validity, boxing and defensive copies.
- For Burst/Jobs, require unmanaged/blittable data and explicit NativeContainer ownership/dependency completion.
- Editor success is not Player/IL2CPP proof.

## Shader boundary

ShaderLab/HLSL/Compute/RendererFeature/RenderGraph work must use `SkillReferences/SHADER_PERFORMANCE_STANDARDS.md` and the dedicated Shader Agents. C# rules cover script-side property IDs, keywords, pass/kernel names, buffers and material contracts, but do not replace GPU performance analysis.

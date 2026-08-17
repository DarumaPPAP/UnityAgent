# Unity C# Code Formatting Standards

## Purpose

UnityAgentが生成・修正するC#の見た目をモデル依存にせず、短い式を不必要に縦へ分割しない一貫したFormattingへ固定する。

この規約は命名規則を変更しない。命名の正本は`SkillReferences/CODING_STANDARDS.md`とし、private fieldの`_camelCase`、enum typeの`E_UPPER_SNAKE_CASE`、struct typeの`S_UPPER_SNAKE_CASE`、constの`SCREAMING_SNAKE_CASE`を維持する。

## 1. Core principle

- 1行で自然に読める式は1行で書く。
- 改行は装飾ではなく、可読性または意味の分離が必要な場合だけ行う。
- `=`の直後で機械的に改行しない。
- 短いMethod CallやProperty accessを縦方向へ分解しない。
- 既存Projectに明示的なFormatterまたはStyleがある場合はProject固有規約を優先する。

## 2. Assignment

短い代入は1行にする。

```csharp
_cameraData = camera.GetUniversalAdditionalCameraData();
_defaultAntiAliasing = _cameraData.antialiasing;
_urpAsset = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
```

次のような改行は原則禁止する。

```csharp
_cameraData =
	camera.GetUniversalAdditionalCameraData();

_defaultAntiAliasing =
	_cameraData.antialiasing;
```

右辺が長く、1行では明らかに読みづらい場合のみ意味単位で改行する。

## 3. Method calls and chains

短い呼び出しは1行にする。

```csharp
_cameraData = camera.GetUniversalAdditionalCameraData();
RestoreDefaultSettings();
```

Method Chainは短い場合は1行、複数段の処理を読む必要がある場合だけ`.`の境界で改行する。

```csharp
var result = source.Where(IsValid).Select(Convert).ToArray();
```

長い場合:

```csharp
var result = source
	.Where(IsValid)
	.Select(Convert)
	.ToArray();
```

短いchainを1呼び出しごとに縦へ積まない。

## 4. Conditions

短い条件は1行にする。

```csharp
if (_urpAsset == null)
{
	return;
}
```

複数条件で1行が読みづらい場合だけ、論理演算子単位で改行する。

```csharp
if (isCameraEnabled &&
	isUrpEnabled &&
	hasValidSettings)
{
	ApplySettings();
}
```

開き括弧直後だけを理由に条件を改行しない。

## 5. Arguments

短い引数列は1行にする。

```csharp
Debug.LogError(message, this);
```

引数が長い、引数ごとの意味を分ける必要がある、または1行では読みづらい場合だけ1引数1行へ展開する。

```csharp
CreateSettings(
	camera,
	antiAliasing,
	msaaSampleCount);
```

## 6. Braces

C#の波括弧はAllman Styleを基本とする。

```csharp
if (condition)
{
	Execute();
}
```

Class、Method、Property body、Loop、Conditionも同様とする。

## 7. Indentation

- インデントはTabを基本とする。
- 継続行もProject規約がない限りTabで揃える。
- 空白だけを使った擬似的な縦位置合わせは行わない。

## 8. Blank lines

空行は責務ブロックの区切りに使用する。

- using群とtype宣言の間
- field群とnested typeの間
- Unity Lifecycle method群とpublic/private method群の境界
- 意味の異なる処理ブロック間

単一代入や連続する関連処理の間へ機械的に空行を入れない。

## 9. Member order

MonoBehaviourの既定順は次とする。既存Projectに順序規約がある場合はそちらを優先する。

1. const
2. static readonly / static field（必要な場合のみ）
3. `[SerializeField]` private field
4. public field / property（既存Contractで必要な場合のみ）
5. private runtime field
6. event
7. nested enum / class / struct
8. Unity Lifecycle: `Awake` → `OnEnable` → `Start` → `Update` → `LateUpdate` → `OnDisable` → `OnDestroy`
9. public method
10. private method

存在しない区分のために空の領域やregionを作らない。

## 10. var

型名が短く、Unity Object型やAPI Contractとして型を明示した方が読みやすい場合は明示型を優先する。

```csharp
Camera camera = GetComponent<Camera>();
```

匿名型、非常に長いGeneric型、右辺から型が十分明確で明示型がノイズになる場合は`var`を許可する。

`var`または明示型を機械的に全箇所へ強制しない。

## 11. Attributes

UnityのAttributeは原則1行1Attributeでtypeまたはfieldの直上へ置く。

```csharp
[DisallowMultipleComponent]
[RequireComponent(typeof(Camera))]
public sealed class CameraAntiAliasingSwitcher : MonoBehaviour
```

短いAttributeを横一列へ詰め込まない。

## 12. Comments

Formattingを理由にコメント密度を増やさない。コメントは`SkillReferences/JAPANESE_CODE_COMMENT_STANDARDS.md`を正本とし、理由、制約、所有権、寿命、実行順、破綻条件を必要な場合だけ記述する。

## 13. Formatting guard examples

### Preferred

```csharp
private void Awake()
{
	Camera camera = GetComponent<Camera>();
	_cameraData = camera.GetUniversalAdditionalCameraData();
	_urpAsset = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;

	if (_urpAsset == null)
	{
		return;
	}

	_defaultAntiAliasing = _cameraData.antialiasing;
	_defaultMsaaSampleCount = _urpAsset.msaaSampleCount;
}
```

### Avoid

```csharp
private void Awake()
{
	Camera camera =
		GetComponent<Camera>();

	_cameraData =
		camera.GetUniversalAdditionalCameraData();

	_urpAsset =
		GraphicsSettings.currentRenderPipeline
		as UniversalRenderPipelineAsset;
}
```

## 14. Review checklist

- [ ] 1行で自然に読める代入を不必要に折っていない
- [ ] `=`の直後で機械的に改行していない
- [ ] 短いMethod Call / Property accessを縦へ分解していない
- [ ] 条件や引数は必要な場合だけ意味単位で改行している
- [ ] Allman StyleとTab indentationを守っている
- [ ] Member orderが既定またはProject規約に従っている
- [ ] Formatting変更を理由に命名規則を変更していない

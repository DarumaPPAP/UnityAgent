---
name: japanese-code-comment-common
description: Unity、C#、ShaderLab、HLSL、Compute Shader向け日本語コメントの共通原則を定義する。本番用・学習用Skillから参照する。
---

# Japanese Code Comment Common

1. コメントは日本語で記述する。
2. コードから自明な処理を日本語へ置き換えただけのコメントは書かない。
3. コメントは優先順に「理由」「制約」「意図」「副作用」「破綻条件」「所有権」「寿命」を説明する。
4. コメントと実装が矛盾する場合は、コメントではなく実装と仕様を確認して整合させる。
5. Unity API、URP、RenderGraph、Burst、Jobs、IL2CPP、Shaderの挙動を推測で断定しない。
6. 性能改善率、GPU時間、GC削減量などの数値は、実測または明示された根拠がある場合だけ書く。
7. 根拠が未確認の場合は「想定」「可能性」「要計測」と明示する。
8. コメント追加を理由に、コード構造、公開API、シリアライズ、Shader Property、Keyword、Pass、RenderStateを変更しない。
9. `TODO`、`FIXME`、`NOTE`、`WORKAROUND`は、理由と解除条件または確認条件を併記する。
10. 同じ説明をクラス、メソッド、行コメントで重複させない。

## CRF for Code

局所的な設計判断、制約、バグ回避、最適化意図には、必要に応じて次の順序を使用する。

1. Conclusion: 実装方針、禁止事項、保持条件。
2. Reason: なぜ必要か。
3. Fact / Constraint / Failure Condition: 仕様、実測、再現条件、変更時の破綻。

すべての要素を強制しない。根拠がない場合はConclusionとReasonだけで終了する。

## SDS for Code

クラス全体、主要メソッド、複数段階の処理説明には、必要に応じて次の順序を使用する。

1. Summary: 何を実現するか。
2. Details: 処理順、入力、出力、依存関係、制約。
3. Summary: 読み手が保持すべき要点。

短いインラインコメントへSDSを機械的に適用しない。

## Comment Levels

- Level 0: 自明な処理。コメントなし。
- Level 1: 理由を1行で示す短縮CRF。
- Level 2: バグ回避、実行順、寿命、性能意図を示す完全CRF。
- Level 3: クラスまたは主要メソッドを説明するSDS。
- Level 4: 学習用としてSDS、CRF、代替案、注意点まで説明する。

## Prohibited Examples

```csharp
// カウントを1増やす
_count++;
```

```csharp
// nullならreturn
if (_material == null)
{
    return;
}
```

## Preferred Example

```csharp
// PreviewCameraではMaterial Inspector更新時にもPassが実行されるため除外する。
if (cameraData.cameraType == CameraType.Preview)
{
    return;
}
```

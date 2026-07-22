---
name: production-code-comments
description: Unity本番コードへ、保守・変更・障害調査に必要な最小限の日本語コメントを追加する。コードから自明な説明は書かない。
---

# Production Code Comments

1. `.agents/skills/japanese-code-comment-common/SKILL.md`を読む。
2. コメント量の最大化ではなく、変更時の事故防止と保守性を目的とする。
3. 基本はLevel 1またはLevel 2のCRF形式とし、通常1〜3行に収める。
4. public型とpublic APIには、責務、前提条件、副作用、例外、寿命が外部利用者へ必要な場合だけXMLドキュメントコメントを付ける。
5. privateメソッドへ一律にXMLコメントを付けない。

## Required Targets

次の箇所には、コードだけで意図が読み取れない場合にコメントを付ける。

- Unityライフサイクルと実行順への依存。
- `ScriptableRendererFeature`、`ScriptableRenderPass`、RenderGraph Passの挿入位置。
- TextureHandle、RTHandle、NativeContainer、ComputeBufferなどの所有権と寿命。
- Color、Depth、Motion Vector、History、Reactive MaskのRead/Write関係。
- Editor、Player、SceneView、PreviewCamera、XR、IL2CPP、Console固有の分岐。
- Allocation、コピー、boxing、同期、描画回数、Texture Sample削減などの性能意図。
- 非自明な数式、座標空間、前フレーム値の更新順。
- バグ回避、互換性維持、一見不要に見える処理。
- 変更すると破綻する条件またはRevert条件。

## Do Not Comment

- 変数名、メソッド名、条件式を日本語へ言い換えただけの説明。
- すべての`if`、`for`、`return`、代入、getter、setter。
- 「念のため」「一応」「高速化のため」だけで根拠がない説明。
- 未計測の性能改善率。
- Unity内部実装への推測。
- 古い仕様や削除済み処理の履歴。履歴はGitへ残す。

## CRF Pattern

```csharp
// 前フレーム行列はPass実行後に更新する。
// 描画前に更新すると現在フレーム同士を比較し、Motion Vectorが0付近になるため。
_previousViewProjection = currentViewProjection;
```

```hlsl
// 遠距離では高周波の波形計算を省略する。
// 投影後の視覚差が小さい領域でTexture Sampleを削減するため。
// 距離境界が細かく交差する場合はWave divergenceを計測すること。
```

## XML Documentation

- `summary`: 名前の言い換えではなく責務を書く。
- `param`: 値の意味、単位、座標空間、null許容、所有権を書く。
- `returns`: 戻り値の意味と寿命を書く。
- `remarks`: 呼び出し順、制約、副作用、非対応条件を書く。
- `exception`: 呼び出し側が対処可能な例外だけを書く。

## Completion Gate

生成または修正後に次を確認する。

1. コメントなしでは誤変更しやすい箇所が説明されているか。
2. コードを復唱するだけのコメントが残っていないか。
3. コメントと実装が一致しているか。
4. 性能、Unity API、GPU挙動を根拠なく断定していないか。
5. コメント削除後も読める命名と構造になっているか。

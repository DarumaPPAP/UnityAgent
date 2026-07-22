---
name: learning-code-comments
description: Unity、C#、ShaderLab、HLSL、RenderGraphコードへ、処理順、API、データフロー、設計理由を理解するための日本語学習コメントを追加する。
---

# Learning Code Comments

1. `.agents/skills/japanese-code-comment-common/SKILL.md`を読む。
2. 初見の開発者が処理の入口、順序、入出力、依存関係、制約を追える状態を目標とする。
3. クラスと主要メソッドにはLevel 3のSDS、局所的な設計判断にはLevel 1またはLevel 2のCRFを使用する。
4. 複雑な概念ではLevel 4として、代替案、不採用理由、注意点、アナロジーを追加してよい。
5. 行単位の逐語解説ではなく、意味のある処理ブロック単位で説明する。

## Class Overview

クラス冒頭では必要に応じて次を説明する。

1. 何を実現するクラスか。
2. UnityまたはShader Pipeline上のどこで動くか。
3. 処理順序。
4. 主な入力と出力。
5. 利点。
6. 制約と非対応条件。

## Method Overview

主要メソッドでは必要に応じて次を説明する。

- Unityから呼ばれるタイミング。
- 呼び出し元と次に進む処理。
- 入力値の意味、単位、座標空間、寿命。
- 戻り値と副作用。
- CPU処理かGPU処理か。
- 失敗しやすい変更点。

## Unity and Rendering Topics

次の内容は初出時に短く説明する。

- `Awake`、`OnEnable`、`Start`、`Update`、`LateUpdate`の役割差。
- Editor、Player、SceneView、PreviewCameraの違い。
- RenderGraphのPass依存、Read/Write宣言、TextureHandleの寿命。
- RendererList、RenderQueue、Layer、ShaderTag、LightModeの役割。
- Color、Depth、Motion Vector、Historyのデータフロー。
- Object、World、View、Clip、NDC、Screen、UV座標空間。
- Vertex、Fragment、Computeの実行単位。
- `half`、`float`、動的分岐、Texture Sampleの利点と欠点。
- Burst、Jobs、NativeContainerの所有権と依存関係。

## SDS Pattern

```csharp
/// <summary>
/// 透明オブジェクトを低解像度で描画し、カメラカラーへ合成するRendererFeatureです。
/// </summary>
/// <remarks>
/// 対象抽出、低解像度描画、アップスケール、合成の順に処理します。
/// Fragment実行数を減らせますが、細い輪郭や高周波模様は失われる可能性があります。
/// そのため、画質低下を許容できる透明表現だけを対象にします。
/// </remarks>
```

## Local CRF Pattern

```csharp
// TextureHandleはRenderGraphが管理するフレーム内限定の論理ハンドルです。
// 次フレームでは有効性を保証できないため、RendererFeatureのフィールドへ保存しません。
var color = renderGraph.CreateTexture(descriptor);
```

## Analogy Rule

アナロジーは複雑な概念の補助に限定し、技術的説明の代替にしない。

例:

```csharp
// RenderGraphへのRead/Write宣言は、使用するリソースを事前予約して
// 工程表を組み立ててもらうイメージです。
// 実際には宣言情報からPass順序とTexture寿命が決定されます。
```

## Detail Control

- 同じ専門用語を同一ファイルで繰り返し説明しない。
- 単純な代入、明確なnullチェック、名前から分かる呼び出しは説明しない。
- コメントがコード本体を分断する場合は、クラス概要またはMarkdown解説へ移す。
- 本番投入コードへ学習コメントを追加する場合は、`production-code-comments`との差分を意識して冗長さを抑える。

## Completion Gate

1. 処理の入口から終了まで追えるか。
2. データがどこから来て、どこへ渡るか分かるか。
3. Unity APIやShader処理の役割が初見でも理解できるか。
4. 設計理由と代替案が区別されているか。
5. 推測と確定仕様が区別されているか。
6. コメントがコードの単純な復唱になっていないか。

# Japanese Code Comment Standards

Unity、C#、ShaderLab、HLSL、Compute Shader向け日本語コメントの正本規約。

## 共通原則

1. コメントは日本語で記述する。
2. コードから自明な処理を日本語へ置き換えただけのコメントは書かない。
3. 「理由」「制約」「意図」「副作用」「破綻条件」「所有権」「寿命」を優先する。
4. コメントと実装が矛盾する場合は、仕様と実装を確認して整合させる。
5. Unity API、URP、RenderGraph、Burst、Jobs、IL2CPP、Shaderの挙動を推測で断定しない。
6. 性能改善率、GPU時間、GC削減量は、実測または明示された根拠がある場合だけ書く。
7. 根拠が未確認なら「想定」「可能性」「要計測」と明示する。
8. コメント追加を理由に公開API、シリアライズ、Shader Property、Keyword、Pass、RenderStateを変更しない。
9. `TODO`、`FIXME`、`NOTE`、`WORKAROUND`には理由と解除条件または確認条件を書く。
10. 同じ説明をクラス、メソッド、行コメントで重複させない。

## CRF for Code

局所的な設計判断、制約、バグ回避、最適化意図には必要に応じて次を使う。

1. Conclusion: 実装方針、禁止事項、保持条件。
2. Reason: なぜ必要か。
3. Fact / Constraint / Failure Condition: 仕様、実測、再現条件、変更時の破綻。

全要素を強制しない。根拠がない場合はConclusionとReasonだけで終える。

## SDS for Code

クラス全体、主要メソッド、複数段階の処理説明には必要に応じて次を使う。

1. Summary: 何を実現するか。
2. Details: 処理順、入力、出力、依存関係、制約。
3. Summary: 読み手が保持すべき要点。

短いインラインコメントへSDSを機械的に適用しない。

## コメントレベル

- Level 0: 自明な処理。コメントなし。
- Level 1: 理由を1行で示す短縮CRF。
- Level 2: バグ回避、実行順、寿命、性能意図を示す完全CRF。
- Level 3: クラスまたは主要メソッドを説明するSDS。
- Level 4: 学習用としてSDS、CRF、代替案、注意点まで説明する。

## Productionプロファイル

- Level 1またはLevel 2を基本とし、通常1〜3行に収める。
- コメント量の最大化ではなく、変更時の事故防止と保守性を目的とする。
- public APIには、外部利用者へ必要な責務、前提条件、副作用、例外、寿命だけをXMLドキュメントで示す。
- privateメソッドへ一律にXMLコメントを付けない。
- Unityライフサイクル、Pass実行順、リソース所有権と寿命、Read/Write関係、実機差、性能意図、座標空間、バグ回避を優先する。
- 変数名、条件式、代入、getter、setterの復唱、未計測の効果、Unity内部実装の推測、Git履歴の代替コメントは禁止する。

### Production例

```csharp
// 前フレーム行列はPass実行後に更新する。
// 描画前に更新すると現在フレーム同士を比較し、Motion Vectorが0付近になるため。
_previousViewProjection = currentViewProjection;
```

## Learningプロファイル

- クラスと主要メソッドにはLevel 3のSDS、局所的な設計判断にはLevel 1またはLevel 2のCRFを使う。
- 複雑な概念ではLevel 4として、代替案、不採用理由、注意点、アナロジーを追加してよい。
- 行単位ではなく、意味のある処理ブロック単位で説明する。
- クラス冒頭では目的、Pipeline上の位置、処理順、入力、出力、利点、制約を必要に応じて説明する。
- 主要メソッドでは呼び出し時期、入力、出力、副作用、CPU/GPU、失敗しやすい変更点を説明する。
- 初出時にRenderGraph依存、TextureHandle寿命、RendererList、RenderQueue、LightMode、座標空間、Vertex/Fragment/Compute、精度型、分岐、Texture Sample、Burst/Jobsの所有権を短く説明する。
- アナロジーは技術的説明の補助に限定する。
- 学習用コメントが本番コードを分断する場合はMarkdown解説へ移す。

### Learning例

```csharp
// TextureHandleはRenderGraphが管理するフレーム内限定の論理ハンドルです。
// 次フレームでは有効性を保証できないため、RendererFeatureのフィールドへ保存しません。
var color = renderGraph.CreateTexture(descriptor);
```

## XMLドキュメント

- `summary`: 名前の言い換えではなく責務を書く。
- `param`: 値の意味、単位、座標空間、null許容、所有権を書く。
- `returns`: 戻り値の意味と寿命を書く。
- `remarks`: 呼び出し順、制約、副作用、非対応条件を書く。
- `exception`: 呼び出し側が対処可能な例外だけを書く。

## 禁止例

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

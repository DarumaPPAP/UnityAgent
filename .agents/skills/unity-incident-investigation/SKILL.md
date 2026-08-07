---
name: unity-incident-investigation
description: Use when investigating a Unity compile error, exception, regression, rendering breakage, Editor-versus-Player difference, platform-only failure, or behavior that previously worked. Establishes observations and evidence, ranks hypotheses, isolates one causal change, and hands a confirmed minimal fix to the appropriate implementation Skill. Does not perform speculative multi-file refactors.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  version: "1.1.0"
---

# Unity Incident Investigation

不具合対応を「とりあえず修正」ではなく、観測、仮説、反証、最小修正の順で進める。
原因が確定するまではRead-only調査を優先する。

## When to use

- C#コンパイルエラー、Assembly Definition、Package、API差分
- NullReferenceException、InvalidOperationException、ライフサイクル依存
- Editorでは正常だがPlayer、IL2CPP、Console実機で壊れる
- Shader、Material、RenderQueue、Pass、Depth、Motion Vector、Transparentの表示破綻
- 変更後に以前の挙動が壊れた回帰
- 性能悪化の発生箇所を特定したいが原因が未確定

性能改善案の比較だけなら、先に対応するAudit Skillを使う。新機能の要件定義には使わない。

## Delegates to

- C#原因調査: `csharp-antipattern-audit`
- C#最小修正: `csharp-safe-patch`または`unity-implement`
- URP / RenderGraph / RendererFeature: `unity-rendering`
- Shader / HLSL原因調査: `shader-performance-auditor`
- Shader修正: `shader-performance-refactor`
- Variant / Strip / Strict Variant: `unity-shader-variant-governor`
- Before/After: `unity-runtime-evidence`または`shader-runtime-evidence`
- High-risk Fresh-context review: `unity-doubt-review`
- 修正後レビュー: `unity-review`

## Step 1 — Freeze the observation

最初に、解釈を混ぜず観測事実を固定する。

- Expected behavior
- Actual behavior
- Exact error / warning / visual symptom
- First bad version or last known good state
- Reproduction steps and frequency
- Unity version / package version / render pipeline
- Editor or Player
- Mono or IL2CPP
- Development or Release
- Platform and graphics API
- Scene, camera, quality, renderer, material, prefab conditions
- Relevant log, stack trace, Frame Debugger, RenderDoc, Profiler evidence

ログがある場合は、先に最初の原因候補となるエラーを読む。後続の連鎖エラーを根因扱いしない。

## Step 2 — Define the incident boundary

調査対象を一文で定義する。

> `<条件>`で`<操作>`すると、`<期待>`ではなく`<実際>`になる。

さらに次を明示する。

- In scope: 今回確認するファイル、Subsystem、Pass、Object
- Out of scope: 同時に直さない別問題
- Compatibility contracts: public API、Serialized Data、Prefab/Scene、Shader契約
- Success condition: 何が再現しなくなれば解決か

長期保存が必要な障害だけ、`Specs/<FeatureName>/incidents/<IncidentId>.md`へ記録する。単発の局所修正へ不要な文書を増やさない。

## Step 3 — Build a ranked hypothesis ledger

仮説ごとに次を持つ。

| Field | Meaning |
|---|---|
| Hypothesis | 原因候補 |
| Supporting evidence | 支持する観測 |
| Contradicting evidence | 反証または不足 |
| Cheapest test | 最小の切り分け方法 |
| Risk | 誤修正した場合の影響 |
| Status | Open / Rejected / Confirmed |

仮説は確度順に並べる。コードの見た目だけでConfirmedにしない。

## Step 4 — Investigate in Unity-specific order

### 4.1 Compile and import boundary

- 最初のコンパイルエラー
- Assembly Definition参照とEditor/Runtime分離
- Package/API version mismatch
- Conditional compilation symbol
- Asset import、Domain Reload、Script Reload順序

### 4.2 Serialization and asset boundary

- SerializeField名・型変更
- Missing Script、Prefab override、Scene参照
- Material Property、Shader reassignment、renderQueue reset
- Addressables、Resources、AssetBundle、stripping

### 4.3 Lifetime and ownership boundary

- Awake / OnEnable / Start / Update / LateUpdate / OnDisable / Dispose順序
- 所有者不明のResource、NativeContainer、RenderTexture、CommandBuffer
- static状態、event解除漏れ、重複登録
- Object破棄後参照、Scene切替、Domain Reload無効

### 4.4 Rendering boundary

- Camera、Renderer Data、RenderPassEvent
- FilteringSettings、RenderQueueRange、LayerMask、ShaderTagId
- RendererList対象とOverride Materialの意味
- Color / Depth attachment、Load/Store、MSAA、format
- RenderGraph resource lifetimeとGlobal State
- Shader Pass、LightMode、Cull、ZWrite、ZTest、Blend、ColorMask
- Transparent sorting、背面描画、Outline、MotionVectors

### 4.5 Player and platform boundary

- Editor-only API
- IL2CPP/AOT、Reflection、generic instantiation、stripping
- Graphics API、precision、unsupported format
- Strict Variant、Shader Warmup、AssetBundle差
- Development/Release、platform define、実機メモリ制約

### 4.6 Performance boundary

- 回帰したCPU/GPU marker
- Allocation、Renderer count、SetPass、Overdraw、Bandwidth
- Editor負荷をPlayer負荷として扱っていないか
- 同条件のBefore/After captureが存在するか

## Step 5 — Run the cheapest discriminating test

仮説を一つ選び、他の条件を固定した最小テストを行う。

良いテスト例:

- 問題の代入直前・直後でMaterial、Shader、RawQueue、ActualQueueを記録する
- RendererFeatureを丸ごと外さず、対象Passだけ無効化する
- EditorとPlayerで同じ設定値を出力する
- 問題ShaderのPass/KeywordだけをFrame Debuggerで確認する
- 一つ前のcommitと対象ファイルだけを比較する

悪いテスト例:

- 関連しそうな複数クラスを一斉に書き換える
- 新しいManagerやFallbackを追加して症状を隠す
- 例外をcatchして継続させる
- Debug設定を変えた結果だけで根因を断定する

## Step 6 — Confirm causality before patching

Confirmedの条件:

1. 仮説から予測できる観測がある。
2. 最小テストで症状が再現または消失する。
3. 競合仮説より説明力が高い。
4. 修正対象と症状の因果経路を説明できる。

証拠不足ならHigh confidenceまたはEvidence requiredに留める。

## Step 6.5 — High-risk doubt gate

次のいずれかに該当する場合、Mutationまたは完成判定の前に`unity-doubt-review`へFresh-context reviewを委譲する。

- Editor / Player / Console実機差が原因または受け入れ条件に含まれる
- Rendering、Lighting、Addressables、Serializationなど変更波及が広い
- public / serialized / Shader契約へ影響する
- Regression historyがある
- 複数の競合仮説がまだ成立する
- 性能値またはVisual Evidenceを採用判断へ使う

`unity-doubt-review`が`Rework`ならStep 3へ戻る。`Inconclusive`なら未検証Gateを明示して、検証済みと報告しない。
Low-riskかつ原因・変更境界が明確な局所修正へ、このGateを儀式的に強制しない。

## Step 7 — Apply one minimal fix

- Confirmed仮説に直接対応する箇所だけを変更する。
- 既存契約を保持する。
- 症状を隠すのではなく、原因となる状態遷移または設定を修正する。
- 追加の設計改善は別Taskへ分離する。
- 修正後に同じ再現手順を実行する。

## Step 8 — Regression check

最低限、次を確認する。

- 元の再現手順
- 正常系
- 境界値または無効設定
- Editor / Player差が関係する場合は両方
- Rendering変更では対象外Queue、Layer、Camera、Pass
- Serialization変更では既存Prefab/Scene/Save Data

## Anti-Rationalization

| よくある判断 | 実際のルール |
|---|---|
| 「症状が消えたので根因確定」 | 因果経路と反証テストが必要 |
| 「Editorで直ったから完了」 | Player / 実機依存の主張には対応Evidenceが必要 |
| 「ついでに整理すると綺麗」 | Confirmed cause外の変更は別Task |
| 「将来使うのでInterface化」 | 実在するVariation Axisがなければ追加しない |
| 「計測できないが改善するはず」 | 未計測を改善済みと報告しない |

## Output contract

- Incident statement
- Environment and reproduction
- Confirmed observations
- Hypothesis ledger
- Root causeまたは現時点の確度
- Doubt review decision when required
- Changed files and exact fix
- Preserved contracts
- Verification performed
- Remaining evidence required
- Revert condition

## Checklist

- [ ] Expected / Actualを分離した
- [ ] 最初の原因エラーを確認した
- [ ] Incident boundaryを一文で定義した
- [ ] 仮説を確度順に並べた
- [ ] 一つの仮説だけを切り分けた
- [ ] 因果確認後に最小修正した
- [ ] High-risk条件ではFresh-context doubt reviewを行った
- [ ] 同じ再現手順で再検証した
- [ ] 未実施のPlayer/実機確認を明記した

## Common mistakes

- Stack traceの最後の行だけを直す。
- EditorとPlayerの条件差を記録しない。
- Materialの表示名が同じなので同一状態だと仮定する。
- RenderQueue、Shader、Keyword、Passの実値を確認せずShaderコードを修正する。
- 症状が消えただけで根因確定とする。
- 調査Patchへ設計リファクタリングを混ぜる。
- High-risk変更でPrimary SkillのconfidenceをFresh reviewへそのまま引き継ぐ。

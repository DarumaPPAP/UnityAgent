---
name: unity-review
description: Use when reviewing a Unity implementation, pull request, specification, or completed Task for correctness, compatibility, performance evidence, maintainability, and acceptance readiness. Produces severity-ranked findings and an approve/rework/evidence-required decision. Does not add new features or silently modify reviewed files.
allowed-tools:
  - Read
metadata:
  version: "2.1.0"
---

# Unity Review

Unity変更を、仕様、互換性、実行条件、証拠からRead-onlyで審査する。
レビュー対象へ新機能を追加せず、Findingと受入判定を返す。

## When to use

- PRまたはDiffのコードレビュー
- Feature Taskの完成判定
- 仕様書、Plan、設計案の実現性審査
- C#、Rendering、Shader変更の受入Gate
- 性能改善の証拠が十分か確認

原因未確定の不具合調査は`unity-incident-investigation`を使う。
修正を求められた場合も、Findingを確定してからModifier Skillへ渡す。

## Inputs

- `Policy/User/user-policy.yaml`と今回のユーザー指示
- 対象Projectから検出したFact・Project固有Policy（`Specs/ProjectProfile.md`は未解決FactのFallbackのみ）
- 対象Spec、Plan、Tasks、Task ID
- Diffまたは変更ファイル
- 実行ログ、Test、Profiler、GPU Capture
- 対象Unity / package / Platform / Build条件
- ユーザーが明示した禁止事項と受入条件

## Delegates to

- Unity C#詳細監査: `csharp-antipattern-audit`
- URP / RenderGraph固有確認: `unity-rendering`
- Shader/HLSL詳細監査: `shader-performance-auditor`
- Variant / Strip: `unity-shader-variant-governor`
- C#性能証拠: `unity-runtime-evidence`
- Shader/GPU性能証拠: `shader-runtime-evidence`

## Review order

### Step 1 — Confirm review scope

- 対象TaskまたはRequirement
- 変更ファイル
- 対象外
- 期待する判定
- 利用可能な証拠

対象外の改善案をBlocking Findingにしない。

### Step 2 — Review correctness

- Requirement / ACを満たすか
- 状態遷移、所有権、寿命
- null、例外、破棄、event解除
- Unity lifecycle順序
- Thread / Job / Burst安全性
- Render Pass入出力と依存
- ShaderのRenderStateと計算意味論

### Step 3 — Review compatibility

- public API
- SerializeField、Prefab、Scene、Save Data
- Assembly Definition、Editor/Runtime境界
- IL2CPP/AOT、Reflection、generic、stripping
- Shader Property、Keyword、Pass、LightMode、RenderState
- Material、AssetBundle、Addressables、Resources
- Unity / URP / package version

### Step 4 — Review performance claims

- 対象指標が固定されているか
- Before/Afterが同条件か
- EditorとPlayerを混同していないか
- warm-upとsample countがあるか
- CPU/GPU bottleneckを取り違えていないか
- Target-deviceが必要な主張に実機証拠があるか

静的コードだけで性能改善量を確定しない。

### Step 5 — Review maintainability and scope

- 責務と依存方向
- 仕様外のController、Manager、Profile、Fallback、Debug UI
- 不要なstatic状態
- 巨大差分、無関係な整形、命名変更
- コメントが理由と制約を説明しているか
- 別問題を同じPatchへ混ぜていないか

### Step 6 — Classify findings

Category:

- Correctness
- Compatibility
- Performance
- Maintainability
- Evidence Required

Severity:

- Critical — データ破損、クラッシュ、重大な描画破綻、Release blocker
- Error — 仕様不達、確定バグ、互換性破壊
- Warning — 条件付き問題、将来の高リスク
- Suggestion — 非Blocking改善
- Evidence Required — 実行条件がなく確定できない

各Findingへ次を付ける。

- ID
- Category / Severity
- File and location
- Evidence
- Failure condition
- Impact
- Minimal proposal
- Validation required

### Step 7 — Decide acceptance

- **Approve** — Blocking Findingなし。必要な証拠あり。
- **Approve with non-blocking notes** — Suggestionのみ。
- **Rework** — CriticalまたはErrorあり。
- **Evidence Required** — 実機、Player、Profilerなどがなく受入判断不可。

未検証を「おそらく問題ない」でApproveしない。必要証拠は今回の受入対象とTask Contractから判断する。文書・局所Sourceの審査へ無関係な実機Gateを追加せず、Sourceとしての受入とPlayer/実機/性能の受入を区別する。

## Output contract

- Review target and scope
- Decision
- Findings ordered by severity
- Requirement / AC coverage
- Compatibility status
- Evidence status
- Required fixes
- Non-blocking notes
- Unverified conditions

Findingがない場合も、何を確認し、何を未確認かを書く。

## Scope — what this Skill does not do

- レビュー対象を変更しない。
- 新機能や好みの設計を要求しない。
- 対象外のリファクタリングをBlockingにしない。
- 未計測の性能を承認しない。
- Editor結果だけでConsole実機を保証しない。

## Checklist

- [ ] ScopeとTask/Requirementを固定した
- [ ] CorrectnessとCompatibilityを分離した
- [ ] public/serialized/Shader契約を確認した
- [ ] 性能主張の証拠条件を確認した
- [ ] Findingへ根拠と失敗条件がある
- [ ] BlockingとNon-blockingを分けた
- [ ] 未検証条件を明記した
- [ ] ファイルを変更していない

## Common mistakes

- コードスタイルの好みをErrorとして扱う。
- Spec外の改善を必須修正にする。
- Serialized field変更を通常のrenameとして見逃す。
- RendererFeatureのPass timingやresource lifetimeを確認しない。
- Shaderソースの命令数だけでGPU改善を承認する。
- 実機証拠が必要なのにEditor結果でApproveする。

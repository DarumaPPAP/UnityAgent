---
name: unity-doubt-review
description: Use when a Unity incident, performance change, serialization change, rendering fix, or other high-risk modification has a plausible solution but needs a fresh-context challenge before mutation or acceptance. Re-tests assumptions, seeks contradictory evidence, and returns Proceed, Rework, or Inconclusive. Does not implement fixes or replace the primary investigation Skill.
allowed-tools:
  - Read
metadata:
  version: "1.0.0"
  kind: evidence-gate
  entrypoint: false
  user_policy: .ai/user-policy.yaml
---

# Unity Doubt Review

高リスクなUnity変更で「もっともらしい説明」をそのまま採用しないためのFresh-context Reviewを行う。
Primary Skillの作業をやり直すのではなく、現在の仮説・修正案・Evidenceに対して反証を優先して確認する。

## When to use

次のいずれかで、原因候補または修正案がすでに存在する場合に使う。

- Editor / Player / Console実機で結果が異なる
- Shader、RendererFeature、RenderGraph、Lighting、Addressablesなど描画結果へ広く影響する
- public API、Serialized Data、Prefab、Scene、Save Data互換性を変更する
- Before / Afterの性能差を採用判断へ使う
- Regression historyがあるSubsystemを変更する
- Root causeが一つに見えるが、複数の競合仮説が残っている

単純な説明、局所的なLow-risk fix、原因未調査のIncidentでは使わない。原因未確定なら先に`unity-incident-investigation`を使う。

## Inputs

- Primary Skillが固定したExpected / Actual
- Environmentと再現条件
- Ranked hypotheses
- Proposed fixまたは採用候補
- Supporting evidence
- Contradicting evidence
- Compatibility contract
- 実施済みValidationと未実施Validation

Primary Skillの結論だけを入力にせず、根拠となるSourceまたはEvidenceを直接読む。

## Workflow

### Step 1 — Restate the claim without inheriting confidence

現在の主張を一文にする。

> `<原因>`が`<症状>`を引き起こしており、`<変更>`で`<期待結果>`になる。

Primary Skillのconfidence表現は引き継がず、Evidenceから再評価する。

### Step 2 — Identify the cheapest falsifier

主張が間違っている場合に最も早く発見できる反証テストを一つ選ぶ。

例:

- Shader修正前に実際のPass / Keyword / RenderQueueを確認する
- Lighting修正前にLightingDataAssetとLightmapSettingsの所有状態を比較する
- Editor成功だけなら同条件Player結果を要求する
- GPU最適化なら同一Scene・Camera・Resolution・Quality・warm-up条件のBefore / Afterを比較する

### Step 3 — Generate competing explanations

最低1つ、重大なIncidentでは2つ以上の競合説明を確認する。

各候補に次を付ける。

- Supporting evidence
- Contradicting evidence
- Distinguishing test
- Cost of being wrong

同じ原因の言い換えを別仮説として数えない。

### Step 4 — Check contract blast radius

修正が症状だけでなく次へ影響しないか確認する。

- public / serialized API
- Prefab / Scene / Save Data
- Material / Shader Property / Keyword / Pass
- Renderer / Camera / Queue / Layer
- Addressables / AssetBundle / stripping
- IL2CPP / platform / graphics API
- Resource ownership / lifetime

影響範囲がPrimary SkillのScopeを超える場合はReworkとする。

### Step 5 — Challenge acceptance evidence

次を成功扱いしない。

- Compile成功だけでRuntime成功
- Editor成功だけでPlayerまたは実機成功
- Capture生成だけでVisual Accepted
- 一回のProfiler値だけで性能改善
- 症状消失だけでRoot cause確定
- 未実行Gateを「問題なさそう」でPassed扱い

### Step 6 — Return one decision

- `Proceed`: 主要仮説が反証テストに耐え、必要Evidenceと契約が揃っている
- `Rework`: 競合仮説、Scope漏れ、契約破壊、Evidence不足が具体的に見つかった
- `Inconclusive`: 判断に必要な環境またはEvidenceが利用できない

`Inconclusive`を失敗または成功へ読み替えない。

## Anti-Rationalization

| よくある言い訳 | 判定ルール |
|---|---|
| 「小さい修正だから回帰確認はいらない」 | 変更量ではなく契約とRegression Surfaceで判断する |
| 「Editorで動いたから完成」 | Player / 実機依存の主張には対応Evidenceが必要 |
| 「症状が消えたから原因確定」 | 原因→症状の因果経路と反証テストが必要 |
| 「ついでに整理した方が綺麗」 | Confirmed cause外の変更は別Taskへ分離する |
| 「将来必要になるので抽象化」 | 実在するVariation Axisがなければ追加しない |
| 「Captureが取れたので見た目も合格」 | CaptureはEvidenceでありHuman visual approvalではない |
| 「計測できないが速くなるはず」 | 未計測は`unavailable`または`Inconclusive` |

## Output contract

- Claim under review
- Fresh observations
- Competing explanations
- Cheapest falsifier and result
- Compatibility / blast-radius findings
- Missing evidence
- Decision: Proceed / Rework / Inconclusive
- Reason
- Required next action

## Scope

- Production codeを書かない。
- Primary Skillの代わりにIncident全体を再調査しない。
- Evidenceなしで新しいRoot causeをConfirmedにしない。
- Low-risk作業へ儀式的に強制しない。
- User Policyを一般的Best Practiceで上書きしない。

## Checklist

- [ ] Primary Skillの結論ではなく根拠を直接確認した
- [ ] 最低1つの競合説明を確認した
- [ ] Cheapest falsifierを定義した
- [ ] Compatibility blast radiusを確認した
- [ ] Compile / Editor / Captureを過大評価していない
- [ ] 未実施GateをPassedにしていない
- [ ] Proceed / Rework / Inconclusiveの一つを返した

## Common mistakes

- Primary Skillの文章を言い換えるだけでFresh review扱いする。
- 反証不能な仮説を追加する。
- Sourceを読まずに一般論から反対意見だけを書く。
- Low-risk local fixへ過剰なReview ceremonyを追加する。
- `Inconclusive`を暗黙のProceedとして扱う。

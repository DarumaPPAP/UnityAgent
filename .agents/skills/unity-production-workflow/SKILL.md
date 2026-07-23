---
name: unity-production-workflow
description: Use when a Unity request requires choosing and sequencing multiple workflows — feature implementation, bug fixing, rendering work, performance optimization, migration, or review — especially when the user asks to implement, fix, improve, investigate, optimize, or make a production-ready change without naming the exact Skill. Owns routing, gates, handoffs, and the final evidence report; delegates specialist mechanics instead of duplicating them.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  version: "1.0.0"
---

# Unity Production Workflow

Unity案件の入口となるオーケストレーター。依頼を分類し、必要なSkillだけを順番に呼び出す。
このSkill自身は、C#監査、Shader監査、実測、Spec作成などの専門手順を再定義しない。

## Delegates to

必要なものだけを読む。全Skillを一括で読み込まない。

- `unity-specify` — 新機能または仕様変更の検証可能なSpec
- `unity-plan` — 承認済みSpecから実装Plan
- `unity-tasks` — Planから実行Task
- `unity-implement` — 選択Taskの最小差分実装
- `unity-review` — 仕様、互換性、証拠に基づく変更レビュー
- `unity-incident-investigation` — コンパイルエラー、実行時不具合、描画破綻、回帰調査
- `csharp-antipattern-audit` / `csharp-safe-patch` — Unity C#の監査と安全な修正
- `unity-rendering` — URP、RenderGraph、RendererFeature、Shader/HLSL固有の制約
- `shader-performance-auditor` / `shader-performance-refactor` — Shaderの読取監査と修正
- `unity-shader-variant-governor` — Keyword、Variant、Strip、Strict Variant
- `unity-runtime-evidence` / `shader-runtime-evidence` — Before/After実測
- `production-code-comments` / `learning-code-comments` — 完成コードへの日本語コメント

## Step 1 — Resolve the work contract

最初に、依頼文と利用可能なファイルから次を確定する。

1. **成果物** — 説明、調査結果、Spec、Plan、Task、コード、レビュー、PRのどれか。
2. **変更可否** — Read-onlyか、ファイル変更まで許可されているか。
3. **対象範囲** — 指定ファイル、機能、Task ID、PR、エラー、Shader Passなど。
4. **環境** — Unity、Render Pipeline、対象Platform、Editor/Player、Mono/IL2CPP、Development/Release。
5. **互換性契約** — public API、SerializeField、Prefab/Scene、Save Data、Shader Property、Keyword、Pass、RenderState。
6. **検証可能範囲** — 静的確認、テスト、Unityコンパイル、Editor、Player、実機、Profiler/GPU Capture。

既存ファイルやProject Profileから確定できる内容を質問し直さない。欠落情報が可逆な場合は仮定を明記して進める。
破壊的変更、対象Platform、保存互換性など、誤ると作業全体が無効になる情報だけを停止条件にする。

## Step 2 — Select exactly one primary lane

### Lane A — Explanation / read-only analysis

使用条件:

- 「何をしているか」「原因を説明して」「設計を評価して」
- コード変更を求められていない

処理:

- 対象コードと契約を読む。
- 事実、推論、未確認事項を分離する。
- 実装案を出す場合も、勝手にファイル変更しない。

### Lane B — Incident / regression

使用条件:

- コンパイルエラー、例外、表示崩れ、Editorと実機差、以前は動いた回帰
- 原因が未確定で、修正より先に証拠整理が必要

処理:

- `unity-incident-investigation`を主Skillにする。
- C#なら`csharp-antipattern-audit`、描画なら`unity-rendering`または`shader-performance-auditor`を必要時だけ併用する。
- 原因未確定のまま複数箇所を同時変更しない。

### Lane C — Feature / behavior change

使用条件:

- 新機能、既存仕様変更、複数ファイルの設計変更

処理:

1. Specがなければ`unity-specify`。
2. 変更責務や依存関係が複数なら`unity-plan`。
3. 実行単位が複数なら`unity-tasks`。
4. 選択Taskだけを`unity-implement`。
5. 完了後に`unity-review`。

単一ファイルの局所修正で、要件・変更範囲・受け入れ条件が依頼文から明確な場合は、形式的なPlan/Tasksを増やさず、最小の実装契約を回答内に記録して進めてよい。

### Lane D — Performance optimization

使用条件:

- CPU、GC、GPU、Overdraw、Variant、RenderGraph、描画順、メモリ、ロード時間の改善

処理:

1. 対象指標、再現Scene、Platform、品質設定、計測区間を固定する。
2. Read-only監査を先に行う。
3. 主要仮説を一つに絞る。
4. 最小変更を実装する。
5. `unity-runtime-evidence`または`shader-runtime-evidence`でBefore/Afterを比較する。
6. Adopt / Rework / Revert / Inconclusiveを返す。

計測できていない場合は「改善した」と断定しない。静的に期待される効果と実測済み効果を分離する。

### Lane E — Review / acceptance gate

使用条件:

- コードレビュー、仕様審査、PRレビュー、完成判定

処理:

- `unity-review`を主Skillにする。
- FindingをCorrectness / Compatibility / Performance / Maintainabilityに分ける。
- CriticalまたはErrorが残る場合は承認しない。
- 実機条件が必要なのに証拠がない場合はEvidence Requiredとする。

## Step 3 — Apply the minimum required gates

依頼に関係するGateだけを適用する。

| Work | Required gate |
|---|---|
| C#変更 | `CODING_STANDARDS.md`、必要時にC# Anti-pattern |
| 設計変更 | `ARCHITECTURE_STANDARDS.md` |
| Shader/HLSL | Shader Performance standards + Rule/Refactor policy |
| RendererFeature/RenderGraph | `unity-rendering` |
| Keyword/Strip | `unity-shader-variant-governor` |
| 性能主張 | Runtime Evidence |
| 本番コードのコメント | `production-code-comments` |
| 学習教材 | `learning-code-comments` |

## Step 4 — Execute one bounded change

- 選択Task、指定ファイル、または単一仮説の範囲だけを変更する。
- 仕様外のController、Manager、Fallback、Cache、Debug UI、追加Passを作らない。
- public/serialized/Shader契約を変更する場合は、依頼またはSpecに根拠を持つ。
- 既存の失敗を隠すために例外を握り潰さない。
- 別問題を発見しても、現在の変更に混ぜずFindingまたは次Taskとして分離する。

## Step 5 — Verify at the strongest available level

検証状態を次の階層で報告する。

1. Static inspected
2. Local validator / unit test passed
3. Unity compilation passed
4. Editor reproduction passed
5. Player / IL2CPP passed
6. Target-device measurement passed

実施していない階層を飛ばして「動作確認済み」と表現しない。

## Output contract

最終報告には次を含める。

- Primary laneと使用したSkill
- 対象TaskまたはIncident ID
- 変更ファイル
- 変更理由と主要仮説
- 保持した互換性契約
- 実施した検証
- 未検証事項
- Revert条件または残課題

## Scope — what this Skill does not do

- 専門Skillの手順をコピーしない。
- 依頼されていない新システムを設計しない。
- 新機能へ自動的に巨大なSpec一式を強制しない。
- 原因調査と最適化を同じPatchへ混ぜない。
- Editor上の成功だけでConsole実機を保証しない。

## Checklist

- [ ] 成果物と変更可否を確定した
- [ ] Primary laneを一つ選んだ
- [ ] 必要な専門Skillだけを読んだ
- [ ] 変更境界または主要仮説を一つに限定した
- [ ] 互換性契約を確認した
- [ ] 検証状態を正確に報告した
- [ ] 未検証事項とRevert条件を残した

## Common mistakes

- 依頼を分類せず、いきなりコードを書き始める。
- 小さな修正へ不要なManager、Controller、Profileを追加する。
- バグ調査中に複数の仮説を同時に修正する。
- Shaderのソース行だけでGPU改善量を断定する。
- 実行していないUnityコンパイルや実機検証を完了扱いする。
- 全Skillと全Referenceを毎回読み、コンテキストを浪費する。

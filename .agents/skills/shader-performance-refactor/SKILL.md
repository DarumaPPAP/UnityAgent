---
name: shader-performance-refactor
description: Use when a Shader performance finding has a Rule ID, selected stage/pass, measurable Before state, visual tolerance, and validation plan, and the user wants one small optimization patch. Preserves Shader name, properties, keywords, passes, render state, material compatibility, and image intent. Does not perform unreviewed redesign, stack multiple hypotheses, or permanently edit generated Shader Graph code.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "2.0.0"
---

# Shader Performance Refactor

監査済みShader Findingへ、外部契約と画質を維持した一仮説・一Patchの最適化を適用する。

## Required inputs

- Rule IDまたはConfirmed Finding
- Shader / stage / pass / target location
- Fixed Before state
- Target Platform and graphics API
- Visual tolerance
- External Shader contracts
- Validation and Revert plan

入力が不足する場合は`shader-performance-auditor`へ戻す。

## Required references

- `REFACTOR_POLICY.md`
- `SHADER_REVIEW_GATE.md`
- 対象に応じて`UNITY_URP_POLICY.md`
- Variant変更なら`VARIANT_POLICY.md`

## Workflow

1. Shader name、Properties、Keywords、Pass、LightMode、RenderState、CBUFFERを列挙する。
2. FindingのGPU mechanismと適用条件を再確認する。
3. 一つの主要仮説だけを選ぶ。
4. 最小の意味論維持変更を実装する。
5. Shader compileと対象Variantを確認する。
6. Material、Keyword、Pass、Queue、SRP Batcher互換性を確認する。
7. Image difference、Depth、Motion Vector、Temporal stabilityを確認する。
8. `shader-runtime-evidence`で同条件Before/Afterを比較する。
9. Revert条件と未確認Platformを記録する。

## Output contract

- Rule / Finding ID
- Changed files and location
- Primary hypothesis
- Preserved Shader contracts
- Expected GPU mechanism
- Compile / image / compatibility validation
- Runtime evidence status
- Remaining risk
- Revert condition

## Scope — what this Skill does not do

- 未監査の全面リライトをしない。
- 複数最適化を一Patchへ混ぜない。
- Shader名、Property、Keyword、Pass、RenderStateを無断変更しない。
- 生成Shader Graphコードを恒久編集しない。
- 未計測の改善量を断定しない。

## Checklist

- [ ] Rule/FindingとBefore stateがある
- [ ] 外部Shader契約を列挙した
- [ ] 一つの仮説だけを変更した
- [ ] Compileと対象Variantを確認した
- [ ] Image / Depth / Motion Vectorを確認した
- [ ] Runtime EvidenceとRevert条件を記録した

## Common mistakes

- ALU削減とprecision変更を同時に行う。
- ForwardLitだけ確認し、DepthOnlyやMotionVectorsを壊す。
- local keywordをglobalへ変えてMaterial互換性を壊す。
- `discard`除去で描画結果とOverdraw条件を変える。
- Editor Scene Viewだけで実機採用を決める。

---
name: unity-runtime-evidence
description: Use when deciding whether a Unity C# or runtime-system change should be adopted based on reproducible Before/After evidence for CPU time, GC allocation, memory, scheduling, spikes, Player behavior, IL2CPP, or target-device results. Returns Adopt, Rework, Revert, or Inconclusive. Does not infer missing measurements or substitute Editor data for Player evidence.
allowed-tools:
  - Read
metadata:
  version: "2.0.0"
---

# Unity Runtime Evidence

Unity C#またはRuntime変更を、固定条件のBefore/Afterから採否判定するEvidence Gate。

## Required conditions

- Scene / test case
- Build and commit
- Platform and device
- Editor / Player
- Mono / IL2CPP
- Development / Release
- Quality and frame settings
- Warm-up duration
- Measurement window
- Sample count
- Before and After artifacts

## Workflow

1. 比較条件を固定し、差分を対象変更だけにする。
2. CPU frame time、marker、GC Alloc、memory、job scheduling、spikeを必要範囲で計測する。
3. EditorとPlayer、MonoとIL2CPPを分離する。
4. 平均値だけでなく中央値、上位percentile、最大spikeを目的に応じて確認する。
5. 機能・画質・互換性の回帰を確認する。
6. 条件差または証拠不足を明示する。
7. Adopt / Rework / Revert / Inconclusiveを返す。

## Decision contract

- **Adopt** — 受入条件を満たし、重大な回帰がない。
- **Rework** — 改善傾向はあるが、目標未達または回帰がある。
- **Revert** — 指標悪化、機能破綻、互換性破壊がある。
- **Inconclusive** — 条件不一致、sample不足、対象外noise、必要なPlayer/実機証拠がない。

## Output contract

- Fixed conditions
- Before / After source
- Metrics and sample count
- Functional regression status
- Confidence and limitations
- Decision
- Required next evidence
- Revert condition

## Scope — what this Skill does not do

- 未取得metricを推測しない。
- Editor ProfileをConsole実機結果として扱わない。
- 条件の異なるCaptureを直接比較しない。
- 単一frameだけで一般性能を断定しない。

## Checklist

- [ ] Scene、Build、Platform、Qualityを固定した
- [ ] Warm-upとsample countを記録した
- [ ] Editor/Player、Mono/IL2CPPを分離した
- [ ] Before/Afterが同条件
- [ ] 機能回帰も確認した
- [ ] 判定と限界を記録した

## Common mistakes

- EditorのInspectorやDomain Reload負荷をRuntime回帰へ含める。
- 平均だけを見てframe spikeを無視する。
- BeforeとAfterでQuality、VSync、Render Scaleが違う。
- Development BuildとRelease Buildを直接比較する。
- 証拠不足でも改善扱いする。

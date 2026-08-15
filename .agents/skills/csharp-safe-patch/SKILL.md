---
name: csharp-safe-patch
description: Use when a Unity C# finding has a Rule ID, confirmed failure condition, safe-patch classification, and validation plan, and the user wants the smallest compatible fix. Preserves public API, serialized data, save data, enum values, file identity, execution contracts, naming, and canonical C# formatting. Does not redesign architecture, change sync/async semantics, or fix unrelated findings.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "2.1.0"
---

# C# Safe Patch

承認済みC# Findingへ、互換性を維持した最小修正を適用する。

## Required inputs

- Rule IDまたはConfirmed Finding
- File and location
- Failure condition
- Safe / Review Required / Manual Only
- Compatibility contracts
- Validation plan
- `SkillReferences/CODING_STANDARDS.md`
- `SkillReferences/CODE_FORMATTING_STANDARDS.md`

入力が不足し原因が未確定なら`csharp-antipattern-audit`または`unity-incident-investigation`へ戻す。

## Workflow

1. Findingの根拠と適用条件を再確認する。
2. public API、Serialized fields、enum values、Save Data、file/class identityを列挙する。
3. 一つのPatchへ主要仮説を一つだけ設定する。
4. 意味論を保持する局所編集を優先する。
5. class/struct、sync/async、exception contract、Job dependency graphを自動変更しない。
6. 現行命名規則を維持し、短い代入やMethod Callを不必要に改行しない。
7. Diffに無関係なrename、整形、移動がないか確認する。
8. 指定された最強の検証を実行する。
9. 未解決RiskとRevert条件を記録する。

## Output contract

- Rule / Finding ID
- Changed files
- Exact edit and reason
- Preserved contracts
- Expected effect
- Validation performed
- Unresolved risk
- Revert condition

## Scope — what this Skill does not do

- Findingのない推測修正をしない。
- 複数Findingを一つのPatchへ混ぜない。
- API、Serialization、Save Dataを暗黙に変更しない。
- 設計刷新や新規Managerを追加しない。
- 未計測の性能改善を確定しない。
- Formattingを理由に命名規則を変更しない。
- 短い式を`=`直後で機械的に改行しない。

## Checklist

- [ ] Rule/Finding IDがある
- [ ] Failure conditionを確認した
- [ ] 互換性契約を列挙した
- [ ] 一つの仮説だけを修正した
- [ ] 現行命名規則を維持した
- [ ] Canonical Formattingを維持した
- [ ] 無関係な差分がない
- [ ] 検証とRevert条件を記録した

## Common mistakes

- Allocation削減のためにAPI型を変更する。
- Serialized fieldをrenameしてPrefabを壊す。
- async化を局所最適化として混ぜる。
- Job dependencyを単純化してrace conditionを作る。
- 別Findingをついでに修正する。
- 短い代入を見た目だけのために複数行へ分割する。

---
name: csharp-safe-patch
description: Use when a Unity C# failure is already confirmed or the user explicitly identifies a known local compile error and wants the smallest compatible fix. Preserves public API, serialized data, save data, enum values, file identity, execution contracts, naming, and canonical C# formatting. Does not redesign architecture, change sync/async semantics, or fix unrelated findings.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "2.2.0"
---

# C# Safe Patch

確認済みC# Failureへ、互換性を維持した最小修正を適用する。

## Entry paths

### Confirmed Finding

既存AuditやIncidentからFindingを受け取る場合は、以下を使う。

- Rule IDまたはFinding ID
- File and location
- Failure condition
- Safe / Review Required / Manual Only
- Compatibility contracts
- Validation plan

### User-confirmed local compile error fast path

ユーザーが「指定したC# Fileに既知Compile Errorがあるので、そのErrorだけを直す」と明示している場合、別Auditを必須にしない。

- User instructionをConfirmed Findingの起点として扱う。架空のRule IDは作らない。
- Target sourceを直接読み、Error原因とlocationが一意に確認できる場合だけfast pathを続行する。
- Public / Serialized contractを変えず、Target source内の局所編集だけで解決できることを確認する。
- Safe-patch classificationとvalidation planはSource確認結果からこのAttempt内で作る。
- 原因が複数候補、Source外Dependencyが必要、Public Contract変更が必要な場合はfast pathを停止する。
- Compile環境が利用できないことだけを理由に、Sourceから一意に確認済みの安全な局所Patchそのものを拒否しない。Patch後のCompile状態は`unavailable`として正直に報告する。

両Entry pathで `SkillReferences/CODING_STANDARDS.md` と `SkillReferences/CODE_FORMATTING_STANDARDS.md` を使用する。

## Workflow

1. Entry pathとFinding根拠を確定する。
2. Target sourceを読み、failure locationとfailure conditionを確認する。fast pathではここで一意に確定できなければ停止する。
3. public API、Serialized fields、enum values、Save Data、file/class identityを列挙する。
4. `single_purpose_change` と `preserve_existing_structure` を適用し、一つのPatchへ主要仮説を一つだけ設定する。
5. 意味論を保持する局所編集を優先する。
6. class/struct、sync/async、exception contract、Job dependency graphを自動変更しない。
7. 現行命名規則を維持し、短い代入やMethod Callを不必要に改行しない。
8. Diffに無関係なrename、整形、移動がないか確認する。
9. 利用可能な最強の検証を実行する。Compileを実行できない場合はPASS扱いせず`unavailable`にする。
10. 未解決RiskとRevert条件を記録する。

## Output contract

- Finding source / Rule ID when available
- Changed files
- Exact edit and reason
- Preserved contracts
- Expected effect
- Validation performed
- Unresolved risk
- Revert condition

## Scope — what this Skill does not do

- ユーザー確認もFindingもない推測修正をしない。
- 複数Findingを一つのPatchへ混ぜない。
- API、Serialization、Save Dataを暗黙に変更しない。
- 設計刷新や新規Managerを追加しない。
- 未計測の性能改善を確定しない。
- Formattingを理由に命名規則を変更しない。
- 短い式を`=`直後で機械的に改行しない。
- Compile未実行をCompile PASSとして報告しない。

## Checklist

- [ ] Confirmed Findingまたはuser-confirmed local compile errorである
- [ ] Target fileとFailure conditionをSourceで確認した
- [ ] fast pathなら原因がTarget source内で一意に確定した
- [ ] 互換性契約を列挙した
- [ ] 一つの仮説だけを修正した
- [ ] `single_purpose_change`を維持した
- [ ] `preserve_existing_structure`を維持した
- [ ] 現行命名規則を維持した
- [ ] Canonical Formattingを維持した
- [ ] 無関係な差分がない
- [ ] 検証とRevert条件を記録した

## Common mistakes

- Formal Finding IDが無いことだけを理由に、ユーザーが明示した一意な局所Compile Error修正を拒否する。
- Allocation削減のためにAPI型を変更する。
- Serialized fieldをrenameしてPrefabを壊す。
- async化を局所最適化として混ぜる。
- Job dependencyを単純化してrace conditionを作る。
- 別Findingをついでに修正する。
- 短い代入を見た目だけのために複数行へ分割する。

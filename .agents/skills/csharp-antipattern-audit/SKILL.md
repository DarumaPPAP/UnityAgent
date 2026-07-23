---
name: csharp-antipattern-audit
description: Use when reviewing Unity C# without changing files for correctness, ownership, lifetime, AOT/IL2CPP, Burst/Jobs, allocation, boxing, copying, synchronization, API compatibility, or serialization risks. Produces evidence-ranked findings with Rule IDs and safe-patch classifications. Does not implement fixes or treat profiler-dependent risks as confirmed defects.
allowed-tools:
  - Read
metadata:
  version: "2.0.0"
---

# C# Anti-pattern Audit

Unity C#をRead-onlyで監査し、静的に確定できる問題と実行時計測が必要な問題を分離する。

## When to use

- Unity C#の設計・品質・Allocation監査
- IL2CPP/AOT、Burst/Jobs、Serialization互換性確認
- 修正前にFindingを確定したい
- PRレビューでC#固有の根拠が必要

原因不明の実行時障害は`unity-incident-investigation`をPrimaryにする。確定Findingの修正は`csharp-safe-patch`へ渡す。

## Workflow

1. Unity、Platform、Editor/Player、Mono/IL2CPP、Development/Releaseを確定する。
2. `CODING_STANDARDS.md`、C# Rule、Policyを読む。
3. 仕様、意味論、所有権、寿命、呼び出し頻度を追跡する。
4. public API、Serialized Data、Prefab/Scene、Save Data互換性を確認する。
5. AOT、Thread、Burst/Jobs、NativeContainer、exception contractを確認する。
6. Allocation、boxing、copy、closure、LINQ、毎フレーム探索を条件付きで評価する。
7. FindingをConfirmed / High confidence / Evidence requiredに分類する。
8. SeverityをError / Warning / Suggestion / Evidence Requiredに分類する。
9. 修正可能性をSafe / Review Required / Manual Onlyに分類する。

## Output contract

各Findingに次を含める。

- Rule ID
- File and location
- Evidence
- Required conditions
- Confidence
- Severity
- Runtime or compatibility impact
- Minimal proposal
- Safe-patch level
- Validation required

## Scope — what this Skill does not do

- コードを変更しない。
- `struct`、LINQ、virtual、asyncなどを一律禁止しない。
- 呼び出し頻度不明のAllocationを重大回帰として断定しない。
- Editor条件だけでIL2CPPまたは実機を保証しない。

## Checklist

- [ ] 実行環境と互換性契約を確認した
- [ ] 所有権と寿命を先に確認した
- [ ] 静的確定と実測必要を分離した
- [ ] Findingへ根拠と条件を付けた
- [ ] Safe-patch levelを付けた
- [ ] ファイルを変更していない

## Common mistakes

- `struct`コピーを常に問題扱いする。
- Editor上のGCだけでPlayer性能を断定する。
- Serialized field renameのPrefab/Scene影響を見逃す。
- Burst Jobへmanaged参照が入る条件を確認しない。
- Scannerのパターン一致を確定Findingにする。

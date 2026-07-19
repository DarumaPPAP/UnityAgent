---
name: unity-plan
description: 承認済みUnity Specを、依存関係・変更範囲・検証方法を含む実装Planへ変換する。
---

# Unity Plan

- Read Project Profile, Constitution and feature Spec.
- Define architecture, responsibility, file layout, dependencies, data/resource ownership, migration and validation.
- Preserve existing public/serialized/Shader contracts unless the Spec explicitly changes them.
- Separate implementation phases and identify rollback points.
- For performance work, define Before/After conditions and evidence before implementation.
- Do not write production code during planning.
- Save as `Specs/<FeatureName>/plan.md`.

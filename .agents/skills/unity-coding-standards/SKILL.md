---
name: unity-coding-standards
description: Unity C#実装へ命名、API互換性、IL2CPP、Burst/Jobs、Allocation、例外、async、Architecture選定、C#ファイル粒度規約を適用する。
---

# Unity Coding Standards

Read `SkillReferences/CODING_STANDARDS.md`, `SkillReferences/ARCHITECTURE_STANDARDS.md` and C# anti-pattern policy before implementation or review.

新規Feature、System、ファイル構成、MonoBehaviour / Plain C# / ScriptableObject / ECSの境界が未確定な場合は、`SkillReferences/ARCHITECTURE_DECISION_POLICY.md`と`unity-architecture-design`を使用する。

Resolve environment and call frequency first. Preserve public APIs and serialized contracts. Avoid hidden static lifetime, blocking async, swallowed exceptions, unmeasured hot-path rewrites and unsupported AOT/reflection assumptions.

小規模機能はSingle Cohesive Script Firstとし、新規C#ファイルごとにSplit Reasonを要求する。Pattern適合、hypothetical reuse、Mock可能性、行数だけを理由にController、Service、Interface、Profile、ScriptableObjectや補助ファイルを増やさない。

データ並列処理ではECS、Jobs、Burstを候補から除外せず、ECS Component、Tag、Aspect、Jobを1型1ファイルへ機械的に分割しない。

For Shader/HLSL work, delegate to `unity-rendering` and the Shader Performance skills rather than applying C# rules directly.

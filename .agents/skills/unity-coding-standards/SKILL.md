---
name: unity-coding-standards
description: Unity C#実装へ命名、Formatting、API互換性、IL2CPP、Burst/Jobs、Allocation、例外、async、Architecture選定、C#ファイル粒度規約を適用する。
---

# Unity Coding Standards

Read `SkillReferences/CODING_STANDARDS.md`, `SkillReferences/CODE_FORMATTING_STANDARDS.md`, `SkillReferences/ARCHITECTURE_STANDARDS.md` and C# anti-pattern policy before implementation or review.

新規Type、Architecture Proposal上のPlanned Type、または明示的Type Renameがある場合は`SkillReferences/TYPE_NAMING_STANDARDS.md`も読み、Case Conventionとは別にSemantic Type Naming Reviewを行う。既存Typeを触るだけのLocal FixへNaming Reviewを無条件に適用しない。

新規Feature、System、ファイル構成、MonoBehaviour / Plain C# / ScriptableObject / ECSの境界が未確定な場合は、`SkillReferences/ARCHITECTURE_DECISION_POLICY.md`と`unity-architecture-design`を使用する。

Local Behaviorでは、System級Architecture分析より先にUnity Lifecycle、既存Component、既存Callbackで直接解決できるかを確認する。

Resolve environment and call frequency first. Preserve public APIs and serialized contracts. Avoid hidden static lifetime, blocking async, swallowed exceptions, unmeasured hot-path rewrites and unsupported AOT/reflection assumptions.

小規模機能はMinimum Cohesive Solution Firstとし、新規C#ファイルごとにSplit Reasonを要求する。Pattern適合、hypothetical reuse、Mock可能性、行数だけを理由にController、Service、Interface、Profile、ScriptableObjectや補助ファイルを増やさない。

Semantic Type NamingではReadabilityを短さより優先し、Type NecessityをNamingより先に確認する。Context / Namespace重複、invented abbreviation、Role suffix stacking、Property-level Type proliferationを避ける。LengthはReview TriggerでありHard Limitではない。

ユーザーが具体的なGameObject、Component、Assetを指定している場合、再利用性だけを理由に任意Targetへ一般化しない。Unityまたは既存DomainがSource of Truthを持つ状態を、理由なくprivate fieldへ複製しない。

C# Formattingでは短い代入とMethod Callを1行で記述し、`=`直後の機械的改行を行わない。Formatting変更またはSemantic Naming導入を理由に現行enum / struct / field / const規則を変更しない。

データ並列処理ではECS、Jobs、Burstを候補から除外せず、ECS Component、Tag、Aspect、Jobを1型1ファイルへ機械的に分割しない。

For Shader/HLSL work, delegate to `unity-rendering` and the Shader Performance skills rather than applying C# rules directly.

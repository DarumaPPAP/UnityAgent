# Shader Performance Agent System

## Purpose

Shader性能監査を経験則だけに依存させず、Agent、Skill、Rule ID、計測手順、出力形式へ落とし込む。

## Target

Unity ShaderLab、HLSL、Compute Shader、URP、RenderGraph、Shader Variant、Nintendo Switch/Switch 2/PS4/PS5/PC。

## Non-goals

- 静的解析だけでGPU時間を予測しない。
- 全GPU共通の最適化を自動適用しない。
- Shader Compilerを代替しない。
- Profilerなしで改善率を断定しない。

## Components

- Auditor: Read-only、Rule ID、Confidence、GPU resource、proposal、validation
- Optimizer: audited finding only、external contract preservation、small diff、revertable
- Variant Governor: keyword inventory、Cartesian product、runtime necessity、strip、Strict Variant
- Runtime Evidence: target-device measurement and adoption decision
- Scanner: candidate extraction only; final decision belongs to Agent

## Finding model

RuleId, Severity, Confidence, File, Line, Stage, Resource, Evidence, Explanation, Proposal, Benefit, Risk, Validation.

## Safety

RenderState and Shader-facing names are external contracts. One patch tests one hypothesis. Target Player validation and revert conditions are mandatory for adoption.

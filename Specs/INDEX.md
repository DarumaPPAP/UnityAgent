# Specifications Index

このファイルは `Specs/` 配下のsupporting specificationを一覧管理します。

`Specs/` はUnityAgentのProduction execution authorityではありません。Policy / Orchestration / Context / Runtime / Persistence / Operations / Evalのcanonical contractを置き換えず、Project fallbackや補助Feature仕様を保持します。

## Project / Environment

- [Project Profile](ProjectProfile.md) — Project Factを直接確認できない場合だけ使用するFallback
- [Platform and Environment Fallback Policy](PlatformAndEnvironmentFallbackPolicy.md) — Platform targetとPerformance class、missing environment時の扱い

## Features

| Feature | Status | Spec |
| --- | --- | --- |
| Shader Performance Agent System | Active supporting spec | [spec.md](ShaderPerformanceAgentSystem/spec.md) |

存在しないFeature directoryや削除済みspecをIndexへ残しません。

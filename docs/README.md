# UnityAgent Documentation Index

このIndexは**現在仕様を読む入口**です。過去のMigration、Plan、Review、Decision RecordとCurrent Contractを混同しないために分類しています。

## Current architecture

| Topic | Document |
|---|---|
| 製品境界・Authority・Execution flow | [Architecture](architecture/architecture.md) |
| Production Tool Runtime | [Production Tool Runtime](architecture/production-tool-runtime.md) |
| Specialist Context / Reasoning Handoff | [Specialist Context Assembly](architecture/specialist-context-assembly.md) |
| ArtistSubAgent境界 | [ArtistSubAgent Boundary](architecture/artist-subagent-boundary.md) |
| Full E2E固定Capability | [Full E2E Capability](architecture/full-e2e-capability.md) |
| Hub Catalog Import境界 | [Catalog Import Gate](architecture/catalog-import-gate.md) |
| Local Reference検索 | [Local Reference Navigator](architecture/local-reference-navigator.md) |
| 3分Architecture概要 | [Three Minute Architecture](architecture/three-minute-architecture.md) |

## Development and environment

- [Local Project Development](local-project-development.md)
- [Unity Environment Adaptation](unity-environment-adaptation.md)
- [Context Explorer](context-explorer.md)
- [Unity CLI Reference](references/unity-cli-reference.md)
- [Specifications Index](../Specs/INDEX.md)

## Canonical machine-readable sources

Current behaviorの最終AuthorityはDocumentationではなく以下です。

- `Policy/`
- `Orchestration/`
- `Context/`
- `Runtime/`
- `Persistence/`
- `Operations/`
- `Eval/`
- `Specs/unityagent-layer-contract.yaml`

Documentationと実装が競合した場合は、上記Canonical SourceとTestsを優先してDocumentationを修正します。

## Historical records

次は監査・経緯確認用で、Current behaviorのAuthorityではありません。

- `migration/` — Architecture / Runtime / Baseline移行履歴
- `decisions/` — 日付付きDecision Record
- `superpowers/` — 過去のPlan / Spec
- `architecture/reviews/` — 時点監査
- 日付付き `*-audit-YYYY-MM-DD.md` / `*-decision-YYYY-MM-DD.md`

Historical document内の旧Path、旧Version、旧Support Matrixは当時のEvidenceとして保持し、現在仕様へ読み替えません。

## Documentation maintenance rule

Current docsでは以下を避けます。

- 「current goal」のように短期間で腐る進捗メモ
- 実装済み機能をPilot / 未登録のまま説明する記述
- Historical SupportをCurrent Supportへ混在させる記述
- Registry登録をLive Verification済みとみなす記述
- READMEとArchitectureで同じContractを別定義すること

機能追加・Contract変更時は、実装・Tests・Canonical Schemaの更新後にREADMEとこのIndexから辿れるCurrent documentを同期します。

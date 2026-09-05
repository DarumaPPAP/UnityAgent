---
name: unity-plan
description: Use when an approved Unity Spec must be converted into an implementation design — responsibilities, file boundaries, dependencies, data and resource ownership, compatibility, migration, validation, and rollback. Produces `plan.md`. Does not write production code or silently change the approved requirements.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "2.3.0"
  kind: operation
  entrypoint: false
  user_policy: Policy/User/user-policy.yaml
---

# Unity Plan

承認済みSpecを、実装者が迷わずTaskへ分解できる設計Planへ変換する。
要件を追加せず、責務、依存、所有権、変更範囲、検証方法を具体化する。
「承認済み」は今回の依頼・既存の承認と照合する。計画から実装まで依頼済みなら、Spec/Planごとに形式的な再承認を要求しない。このSkillはPlanを返し、呼出元が依頼された後続工程を継続する。計画だけの依頼では実装しない。Policyが要求する契約変更・破壊的操作の承認は保持する。

## When to use

- 承認済み`spec.md`がある
- 複数ファイルまたは複数Subsystemへ変更が跨る
- public/serialized/Shader契約やMigrationを扱う
- RendererFeature、RenderGraph、Shader、Jobsなど実装境界が重要

要件自体が未確定なら`unity-specify`へ戻す。
単一ファイルの局所修正で変更境界が明確なら、不要なPlanを増やさない。
Primary Domain Routeは`Orchestration/Routing/task-routes.yaml`で選択済みであり、対応する`Context/Selection/context-catalog.yaml`のMaterializationを前提とする。このSkill自身をRouting入口にしない。

## Inputs

1. ユーザーの今回の明示指示
2. `Policy/User/user-policy.yaml`
3. 対象Featureの`spec.md`
4. 関連する既存コード、既存アーキテクチャ、Asset、Prefab、Scene、Shader契約
5. 対象Projectから検出したFactとユーザー確認済みProject Fact
6. 必要Factが未解決の場合だけ`Specs/ProjectProfile.md`をFallbackとして読む
7. 選択Context Packが要求する規約とReference

`Specs/ProjectProfile.md`はFallbackであり、検出済みProject Factや今回ユーザーが確認したFactを上書きしない。
古いPolicy文書を現在のUser Policyへ上書き統合しない。

## Workflow

### Step 1 — Trace requirements to design decisions

各主要設計判断に対応する`FR`、`NFR`、`AC`を付ける。
Specに根拠のない機能、設定、FallbackをPlanへ追加しない。

### Step 2 — Define responsibilities and boundaries

- クラス、struct、ScriptableObject、Pass、Shader Passの責務
- Unityライフサイクル境界
- Runtime / Editor分離
- Assembly Definition境界
- 既存コードの再利用箇所
- 新規ファイルが本当に必要か

`Manager`、`Controller`、`Util`を責務の説明なしで追加しない。
`Single Cohesive Script First`を先に評価し、層分割を一般論だけで正当化しない。

### Step 3 — Define ownership and lifetime

状態またはResourceごとに次を決める。

- Creator
- Owner
- Initialization
- Mutation authority
- Lifetime
- Disposal / release
- Domain Reload / Scene transition behavior

Renderingでは、Texture、Buffer、RendererList、History、Global Stateの寿命と入出力を明示する。

### Step 4 — Define data and compatibility contracts

- public API
- Serialized fields and migration
- Prefab / Scene impact
- Save Data / binary version
- Shader Property / Keyword / Pass / LightMode / RenderState
- Material、AssetBundle、Addressables、Resources
- IL2CPP/AOT/stripping

変更する契約にはMigrationとRollbackを持たせる。

### Step 5 — Define file layout and dependencies

- 変更ファイル
- 新規ファイル
- 読み取り専用Reference
- 外部Package/API
- 依存方向
- 循環依存を作らない境界

各新規C#ファイルに具体的なSplit Reasonを付ける。
パスを推測してUnityプロジェクト構造を新規作成しない。

### Step 6 — Define execution phases

各Phaseへ次を付ける。

- Goal
- Inputs
- Changed files
- Dependency
- Validation
- Rollback point

設計変更と性能仮説を同じPhaseへ混ぜない。

### Step 7 — Define verification

以下から変更契約と受入条件に必要な証拠を選び、必須Gateと条件付き検証を区別する。全区分を一律必須にしない。

- Static validation
- Unit / edit-mode / play-mode test
- Unity compilation
- Editor reproduction
- Player / IL2CPP
- Target-device measurement

性能作業では、実装前にBefore条件、指標、sample、Revert条件を定義する。

### Step 8 — Save the plan

対象Repositoryの正本規則に従って`plan.md`を保存する。
未決定事項またはSpecとの差異は、既存のDecision管理先がある場合だけ記録する。
UnityAgent自身へ製品固有Planを保存しない。

## Required plan sections

- Requirement Traceability
- Current Structure
- Proposed Responsibilities
- Ownership and Lifetime
- File Changes
- Data / Resource Flow
- Compatibility and Migration
- Implementation Phases
- Validation Matrix
- Rollback Strategy
- Decisions / Open Risks

## Output contract

- Plan path
- 対応Requirement ID
- 変更ファイル一覧
- 責務と依存方向
- 所有権と寿命
- 互換性・Migration影響
- PhaseとRollback point
- Tasksへ進める状態かどうか

## Scope — what this Skill does not do

- Production codeを書かない。
- Specにない機能を追加しない。
- 既存契約を暗黙に破壊しない。
- 性能向上を計測前に確定しない。
- 実装Taskを巨大な一件へまとめない。
- 一般的Best PracticeでUser Policyを上書きしない。

## Checklist

- [ ] `Policy/User/user-policy.yaml`を適用した
- [ ] 検出済みProject FactをProject Profileより優先した
- [ ] Project Profileを使用した場合は未解決FactのFallbackとしてのみ使用した
- [ ] 全主要判断がRequirement IDへ追跡できる
- [ ] 責務と依存方向が明確
- [ ] 状態とResourceの所有者・寿命が明確
- [ ] 新規ファイルごとのSplit Reasonがある
- [ ] public/serialized/Shader契約を確認した
- [ ] MigrationとRollbackを定義した
- [ ] Before/After条件を必要時に定義した
- [ ] Production codeを書いていない

## Common mistakes

- PlanへSpec外の便利機能を追加する。
- Project Profileのテンプレート値を検出済みProject Factより優先する。
- 小規模機能へController、Service、Profileを機械的に追加する。
- Unity lifecycle objectへ計算、状態、I/Oを集中させる。
- RenderGraph resourceのCreatorと使用Passだけを書き、寿命と破棄を省く。
- Serialized field変更のPrefab/Scene影響を無視する。
- Platform差を最後の実機確認だけへ押し込む。
- 古いProject Constitutionを現在のPolicyより優先する。

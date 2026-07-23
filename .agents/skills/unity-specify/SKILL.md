---
name: unity-specify
description: Use when defining a new Unity feature or an intentional behavior change before implementation — especially when requirements, target platforms, compatibility constraints, non-goals, or acceptance evidence are not yet explicit. Produces a testable `spec.md` with stable requirement IDs. Does not write production code or choose detailed implementation mechanics.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "2.0.0"
---

# Unity Specify

Unity新機能または仕様変更を、実装判断に使える検証可能なSpecへ変換する。
このSkillは要件と受け入れ条件を所有し、実装コードは書かない。

## When to use

- 「新しい機能を作りたい」「仕様を決めたい」
- 既存挙動を意図的に変更する
- Platform、Render Pipeline、互換性、対象外が未整理
- 複数の実装案を比較する前に、達成条件を固定したい

原因不明の不具合には`unity-incident-investigation`を使う。
Taskと受け入れ条件が既に明確な局所修正へ、形式的なSpecを強制しない。

## Inputs

1. `Specs/ProjectProfile.md`
2. `Specs/ProjectConstitution.md`
3. 関連する既存Spec、コード、ログ、参考資料
4. ユーザーが明示した対象、禁止事項、Target Platform

既に確定している情報を質問し直さない。判断できない内容は推測で確定せず、未決定事項へ残す。

## Workflow

### Step 1 — Define the problem and outcome

- 背景と現在の問題
- 利用者またはSubsystem
- 期待する最終状態
- 今回の成果物

「実装手段」ではなく「満たすべき結果」を先に書く。

### Step 2 — Resolve the Unity environment

必要な範囲で次を確定する。

- Unity / package / Render Pipeline version
- Editor / Player
- Mono / IL2CPP
- Target Platform / graphics API
- Development / Release
- Burst / Jobs / Entities
- Scene、Camera、Renderer、Qualityなどの前提

### Step 3 — Define compatibility contracts

変更してよいものと保持するものを分ける。

- public API
- SerializeField、Prefab、Scene、Save Data
- Assembly Definition、Package依存
- Shader Property、Keyword、Pass、LightMode、RenderState
- AssetBundle、Addressables、Resources、Stripping

### Step 4 — Write testable requirements

- 機能要件: `FR-xxx`
- 非機能要件: `NFR-xxx`
- 受け入れ条件: `AC-xxx`

「高速」「軽量」「安全」「高品質」は、そのまま要件にしない。
計測対象、比較条件、許容値、失敗条件へ変換する。

### Step 5 — Define non-goals and constraints

- 対象外
- 禁止されているController、Manager、Profile、追加Passなど
- 対応しないPlatformまたはPipeline
- 変更不可の既存契約
- 今回行わないMigrationや将来案

### Step 6 — Record unresolved decisions

各未決定事項に、必要な証拠、決定者、実装への影響を書く。
未決定事項を隠して実装可能扱いしない。

### Step 7 — Save and index

- `Specs/<FeatureName>/spec.md`へ保存する。
- `Specs/INDEX.md`へ追加する。
- 既存Specを更新する場合は、変更理由と互換性影響を記録する。

## Required spec sections

- Purpose / Background
- Environment
- Functional Requirements
- Non-functional Requirements
- Compatibility Contracts
- Out of Scope
- Constraints
- Acceptance Criteria
- Verification Matrix
- Open Questions

## Output contract

- Spec path
- 新規または変更したRequirement ID
- 確定した環境と互換性契約
- 明示した対象外
- 未決定事項
- Planへ進める状態かどうか

## Scope — what this Skill does not do

- Production codeを書かない。
- クラス構造やアルゴリズムを最終決定しない。
- ユーザーが禁止した機能をFallbackとして追加しない。
- 未計測の性能値を受け入れ条件として捏造しない。

## Checklist

- [ ] 目的と期待結果が実装手段から分離されている
- [ ] Unity環境が必要な粒度で確定している
- [ ] FR / NFR / ACに安定IDがある
- [ ] 互換性契約と対象外が明記されている
- [ ] 抽象的な品質要求が検証方法へ変換されている
- [ ] 未決定事項が残されている
- [ ] 実装コードを書いていない

## Common mistakes

- ShaderやRendererFeatureの具体構造を先に固定し、目的を後付けする。
- 「Switch対応」を書くだけで実機検証条件を定義しない。
- 既存Prefab、Scene、Material、Save Data互換性を無視する。
- 対象外を記録せず、Agentが親切心で追加実装できる状態にする。
- 小さな局所修正へ不要なSpec一式を強制する。

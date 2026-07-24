# Unity Agent Supervisor Model

UnityAgentの複合依頼を、固定手順ではなく状態遷移として制御するための正本モデル。
`unity-production-workflow`はこのモデルのFlow ownerとして、目的、制約、観測、回復方針を保持し、専門Skillへ必要な処理だけを委譲する。

## 1. Core contract

Supervisorは作業開始前に次の4要素を確定する。

### Goal

最終的に成立させる状態。ファイル生成やコード変更そのものをGoalにしない。

例:

- 指定したRendererFeatureがUnity 6000.3 / URP 17でコンパイルされる
- 既存のShader Property、Pass、RenderStateを維持したまま表示崩れを解消する
- 指定Taskだけを完了し、次Taskへ進まない

### Constraints

変更禁止、互換性契約、対象環境、変更範囲を固定する。

- 変更対象ファイル
- 追加禁止ファイルや禁止責務
- public API、SerializeField、Prefab / Scene、Save Data
- Shader Property、Keyword、Pass、LightMode、RenderState
- Unity、Render Pipeline、Platform、Editor / Player、Mono / IL2CPP

### Observability

成功と失敗を判定する観測手段を定義する。

- Static inspection
- Validator / Unit Test
- Unity compilation
- Console log
- Editor reproduction
- Screenshot / Before-After
- Player / IL2CPP
- Target-device Profiler / GPU Capture

観測手段が存在しない成功条件は、完了条件として扱わない。

### Recovery policy

失敗分類ごとの戻り先、停止条件、Revert条件を定義する。

- Compile failure -> 実装または依存関係の修正へ戻す
- Runtime failure -> Incident調査へ戻す
- Visual failure -> Rendering / Shader調査へ戻す
- Performance failure -> Evidence条件と主要仮説を再設定する
- Scope violation -> Patchを破棄または対象外差分を除去する
- Contract conflict -> 人間判断まで停止する

## 2. Supervisor state machine

| State | 意味 | 主な出力 | 次の状態 |
|---|---|---|---|
| `INTAKE` | 依頼と成果物を受領 | Work Contract候補 | `CONTEXT_REQUIRED` / `READY` / `BLOCKED` |
| `CONTEXT_REQUIRED` | 必須情報または証拠が不足 | 不足項目と取得方法 | `READY` / `BLOCKED` |
| `READY` | Goal、Constraints、Observability、Recoveryが成立 | Execution Contract | `PLANNING` / `IMPLEMENTING` / `INVESTIGATING` |
| `PLANNING` | 複数責務やMigrationを設計 | Spec / Plan / Tasks | `IMPLEMENTING` / `AWAITING_HUMAN_DECISION` |
| `INVESTIGATING` | 原因未確定のIncidentを調査 | 観測、仮説、証拠 | `IMPLEMENTING` / `CONTEXT_REQUIRED` / `BLOCKED` |
| `IMPLEMENTING` | 一つのTaskまたは仮説を最小変更 | Patch | `STATIC_VALIDATION` |
| `STATIC_VALIDATION` | 構造、規約、差分、互換性を確認 | Static findings | `UNITY_VALIDATION` / `IMPLEMENTING` / `REVERT_REQUIRED` |
| `UNITY_VALIDATION` | Compile、Console、Test、Playを確認 | Unity evidence | `DOMAIN_VALIDATION` / `IMPLEMENTING` / `INVESTIGATING` |
| `DOMAIN_VALIDATION` | Rendering、Shader、Variant、AOT等を確認 | Domain evidence | `VISUAL_OR_RUNTIME_VALIDATION` / `IMPLEMENTING` / `INVESTIGATING` |
| `VISUAL_OR_RUNTIME_VALIDATION` | Screenshot、Player、実機、Profilerを確認 | Runtime evidence | `EVIDENCE_REVIEW` / `IMPLEMENTING` / `INVESTIGATING` |
| `EVIDENCE_REVIEW` | Goalと証拠の一致を審査 | Accept / Rework / Revert / Inconclusive | `AWAITING_HUMAN_APPROVAL` / `IMPLEMENTING` / `REVERT_REQUIRED` |
| `AWAITING_HUMAN_DECISION` | 仕様、破壊的変更、品質判断が必要 | 判断材料 | `PLANNING` / `IMPLEMENTING` / `BLOCKED` |
| `AWAITING_HUMAN_APPROVAL` | 機械検証後の最終承認待ち | Evidence package | `ACCEPTED` / `REWORK` |
| `REVERT_REQUIRED` | 安全条件または証拠を満たさない | Revert対象と理由 | `READY` / `BLOCKED` |
| `ACCEPTED` | 承認済み | Commit / PR候補 | 終了 |
| `BLOCKED` | 続行不能 | 停止理由 | 人間または外部証拠待ち |

## 3. Transition rules

### 一本道にしない

`Specify -> Plan -> Tasks -> Implement -> Review`は成果物の順序であり、Supervisorの状態遷移そのものではない。
Compile失敗、表示崩れ、性能未改善、変更範囲超過では、それぞれ別の状態へ戻す。

### 一回の修正で扱う対象を一つにする

- 一つのTask
- 一つのConfirmed Finding
- 一つの主要仮説

原因未確定のまま複数Subsystemを同時変更しない。

### Evidenceを満たすまで完了にしない

コード生成、ファイル更新、Unityコンパイル成功のいずれも単独では完了ではない。
Goalに必要な観測階層をすべて通過して初めて`EVIDENCE_REVIEW`へ進める。

### 次Taskへ自動遷移しない

指定Taskが`ACCEPTED`になっても、次Taskは新しい`INTAKE`として扱う。

## 4. Failure routing

| Observed failure | Primary route | 禁止事項 |
|---|---|---|
| C# compile error | `unity-incident-investigation` + C# specialist | 無関係な全面リファクタリング |
| RenderGraph validation error | `unity-incident-investigation` + `unity-rendering` | Compatibility Modeへの逃避、無関係なController追加 |
| Shader compile / variant missing | `unity-incident-investigation` + Shader / Variant specialist | Shader表現の無関係な変更、SVCへの全Variant収集 |
| Editor / Player差 | `unity-incident-investigation` | Editor結果だけで修正完了扱い |
| Visual mismatch | `unity-rendering`またはShader specialist | コンパイル成功だけで承認 |
| Performance regression / no gain | Runtime Evidence | 静的推測による改善断定 |
| Scope violation | `unity-review` | 対象外差分を残したまま承認 |
| Specification conflict | 人間判断 | Agentによる契約の勝手な変更 |

## 5. Specialist boundaries

Supervisorは専門処理を再実装しない。

- `unity-specify` — 検証可能なGoalと非目標
- `unity-plan` — 責務、依存、Migration、Rollback
- `unity-tasks` — 安定Task IDと変更境界
- `unity-implement` — 選択TaskまたはConfirmed Fixの最小差分
- `unity-incident-investigation` — 観測、仮説、証拠評価
- `unity-review` — 仕様、互換性、差分、証拠の受入Gate
- C# / Rendering / Shader / Variant specialist — Domain固有判断
- Runtime Evidence — Before / AfterとAdopt判定

## 6. Tool exposure policy

巨大な万能Toolセットを常時公開しない。
現在StateとPrimary Skillに必要な操作だけを許可する。

| State | Tool group例 |
|---|---|
| `INTAKE` / `CONTEXT_REQUIRED` | Read、Search、Repository / File metadata |
| `PLANNING` | Read、Write / Edit。実行Toolは原則不要 |
| `IMPLEMENTING` | 対象ファイルのRead、Write / Edit、限定的なShell |
| `STATIC_VALIDATION` | Diff、Validator、Analyzer |
| `UNITY_VALIDATION` | Compile、Console、EditMode / PlayMode Test |
| `DOMAIN_VALIDATION` | Shader compile、Variant、RenderGraph、AOT検査 |
| `VISUAL_OR_RUNTIME_VALIDATION` | Play、Screenshot、Profiler、Target-device evidence |
| `AWAITING_HUMAN_APPROVAL` | Read-only evidence presentation、Git review |

Toolが存在しない場合は実行済みと推測せず、未検証事項として残す。

## 7. Human decision boundaries

次は原則として人間判断を要求する。

- 公開API、Serialization、Save Dataの破壊的変更
- Renderer / Shader Pipelineの設計変更
- 品質と性能のトレードオフ
- 外部Package追加
- ファイル削除または大規模Scene / Prefab変更
- 実機品質の最終承認
- PR Merge

Agentは判断材料、差分、証拠、Revert条件を提出する。

## 8. Execution Contract template

```yaml
goal:
  - 成立させる最終状態

constraints:
  environment:
    unity: ""
    render_pipeline: ""
    platform: ""
  mutation_scope:
    allowed: []
    forbidden: []
  compatibility:
    - 保持する契約

observability:
  static: []
  unity: []
  domain: []
  runtime: []

recovery:
  compile_failure: ""
  runtime_failure: ""
  visual_failure: ""
  performance_failure: ""
  scope_violation: ""
  stop_conditions: []
  revert_condition: ""
```

## 9. Completion evidence package

- Goal達成状況
- 最終State
- Primary lane / Primary Skill
- Task IDまたはIncident ID
- 変更ファイル
- 保持した互換性契約
- 実施した検証階層
- 観測結果と証拠
- 未検証事項
- 失敗時に実行したRecovery
- Revert条件
- 人間判断が必要な項目

## 10. Anti-patterns

- 固定フローを最後まで機械的に通す
- コード生成を完了扱いする
- すべてのToolとSkillを最初から読み込む
- 失敗原因に関係なく実装Agentへ戻す
- Compile成功で表示、性能、実機まで保証する
- Agent自身が仕様や互換性契約を変更する
- 指定Task完了後に次Taskへ自動で進む

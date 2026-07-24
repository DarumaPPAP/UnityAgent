# Execution Contract

複合Unity依頼をSupervisor状態遷移で処理するための作業契約テンプレート。
製品Feature固有の契約は`DarumaPPAP/UnityAIGC-Archive`側の該当SpecまたはIncident記録へ保存する。

## Identification

- Contract ID:
- Task ID / Incident ID:
- Requested outcome:
- Current state:
- Primary lane:
- Primary Skill:
- Secondary Skill:

## Goal

コード生成やファイル更新ではなく、成立させる最終状態を記載する。

- [ ]

## Constraints

### Environment

- Unity:
- Render Pipeline / package version:
- Platform / graphics API:
- Editor / Player:
- Mono / IL2CPP:
- Development / Release:
- Burst / Jobs / Entities:

### Mutation scope

Allowed:

- 

Forbidden:

- 

### Compatibility contracts

- public API:
- SerializeField / Serialization:
- Prefab / Scene:
- Save Data:
- Shader Property:
- Keyword / Variant:
- Pass / LightMode / RenderState:

## Observability

### Static

- [ ] Scope / changed files
- [ ] Namespace / naming
- [ ] Editor / Runtime boundary
- [ ] Dependency / asmdef
- [ ] Compatibility contract

### Unity

- [ ] Validator / unit test
- [ ] Unity compilation
- [ ] Console
- [ ] EditMode Test
- [ ] PlayMode Test

### Domain

- [ ] Rendering / RenderGraph
- [ ] Shader compile
- [ ] Keyword / Variant / Strip
- [ ] AOT / IL2CPP
- [ ] Burst / Jobs

### Runtime / Visual

- [ ] Editor reproduction
- [ ] Screenshot / Before-After
- [ ] Player
- [ ] Target-device
- [ ] Profiler / GPU Capture

## Recovery policy

| Failure class | Return state | Primary route | Stop condition |
|---|---|---|---|
| Compile | `INVESTIGATING` |  |  |
| Runtime | `INVESTIGATING` |  |  |
| Visual | `DOMAIN_VALIDATION` |  |  |
| Performance | `VISUAL_OR_RUNTIME_VALIDATION` |  |  |
| Scope | `REVERT_REQUIRED` | `unity-review` |  |
| Contract conflict | `AWAITING_HUMAN_DECISION` | Supervisor |  |

## Revert condition

- 

## Human decision boundary

- [ ] 公開APIまたはSerializationの破壊的変更
- [ ] Renderer / Shader Pipelineの設計変更
- [ ] 品質と性能のトレードオフ
- [ ] 外部Package追加
- [ ] ファイル削除または大規模Scene / Prefab変更
- [ ] 実機品質の最終承認
- [ ] PR Merge

## Completion evidence

- Final state:
- Goal result:
- Changed files:
- Validation performed:
- Evidence:
- Recovery performed:
- Unverified items:
- Revert condition:
- Human approval required:

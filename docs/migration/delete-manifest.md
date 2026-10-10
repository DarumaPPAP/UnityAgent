# Destructive Delete Manifest

The following paths are removed only after canonical replacements were established and validated:

- `.ai/`
- `src/unityagent/context/compatibility/`
- `eval/compatibility/`
- `tools/BehaviorEval/`
- `tools/GoldenEval/`
- `tools/LoopIntegration/`
- `tests/behavior_eval/`
- `tests/golden_tasks/`
- `tests/loop_integration/`

`src/unityagent/persistence/compatibility/` is removed separately after its historical loader coverage is moved out of the Persistence production authority.

Historical provenance remains under `docs/migration/`, `eval/datasets/`, and `eval/replay/`.

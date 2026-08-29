# Phase 8 destructive delete manifest

The following paths are removed only after canonical replacements were established and validated:

- `.ai/`
- `Context/Compatibility/`
- `Eval/Compatibility/`
- `Tools/BehaviorEval/`
- `Tools/GoldenEval/`
- `Tools/LoopIntegration/`
- `Tests/BehaviorEval/`
- `Tests/GoldenTasks/`
- `Tests/LoopIntegration/`

`Persistence/Compatibility/` is removed separately after its historical loader coverage is moved out of the Persistence production authority.

Historical provenance remains under `docs/migration/`, `Eval/Datasets/`, and `Eval/Replay/`.

---
name: unity-tasks
description: Unity実装Planを、依存関係と完了条件が明確な実行Taskへ分解する。
---

# Unity Tasks

- Read feature Spec and Plan.
- Create small ordered tasks with stable Task IDs.
- Each task states inputs, changed files, dependencies, implementation boundary, validation and done criteria.
- Separate code changes, migration, tests, Unity setup and target-device verification.
- Do not combine unrelated architectural and performance hypotheses.
- Save as `Specs/<FeatureName>/tasks.md`.

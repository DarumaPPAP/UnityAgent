# UnityAgent

Unity向けAI Agent、Skill、コーディング規約、レンダリング規約、Rule Catalog、Prompt、検証Toolを管理する正本リポジトリです。

## Source of truth

- GitHub: Agent、Skill、Standards、Specs、Prompt、Rules、Templates、Tools、Tests
- Google Drive: PDF、PowerPoint、画像、動画、GPU Capture、Profiler Capture、外部調査資料、大容量バイナリ

Google Drive上のコード・規約文書は閲覧用または移行履歴であり、今後の編集正本はこのリポジトリです。

## Main workflow

1. `AGENTS.md`を読む
2. `Specs/ProjectProfile.md`と`Specs/ProjectConstitution.md`を読む
3. 対応する`.agents/skills/<skill>/SKILL.md`を読む
4. 監査と修正を分離する
5. Before / AfterとRevert条件を記録する

## Current systems

- C# Anti-pattern Audit / Safe Patch / Runtime Evidence
- Shader Performance Audit / Refactor / Variant Governance / Runtime Evidence
- Unity 6 / URP / RenderGraph / STP / TAA向け規約

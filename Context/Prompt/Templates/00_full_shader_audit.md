# Shader性能フル監査プロンプト

Google Driveの外部資料と、このリポジトリのCoreResourceを参照して対象Shader一式をRead-only監査してください。

Use:

- `.agents/agents/shader-performance-orchestrator.md`
- `.agents/skills/shader-performance-auditor/SKILL.md`
- `SkillReferences/ShaderPerformance/RULE_CATALOG.md`
- `SkillReferences/ShaderPerformance/UNITY_URP_POLICY.md`
- `SkillReferences/ShaderPerformance/ARCHITECTURE_MATRIX.md`
- `SkillReferences/ShaderPerformance/SEVERITY_MODEL.md`

Requirements:

1. Shader、HLSL、Include、Compute、Material、RendererFeature依存を確認する。
2. Stageと実行頻度を特定する。
3. Rule ID付きFindingを出す。
4. Confidenceを確定／高確度／要計測に分ける。
5. Compiler除去可能性とGPUアーキテクチャ差を記録する。
6. 外部契約を変更しない。
7. 修正は行わず、優先順位と計測計画を提示する。

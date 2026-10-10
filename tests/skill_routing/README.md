# Skill Routing Test Cases

`tests/skill_routing/`は、人間がSkill / Route選択の発火、委譲、Scope Guard、Evidence Guardを確認する手動・補助用Caseです。専門SubAgentやRuntime Providerのインストール・互換性・Project Bindingを検証する場所ではありません。

## Authority

- Semantic Routing: `src/unityagent/orchestration/routing/task-routes.yaml`
- Machine-readable Skill Behavior Contract: `tests/skill_evals/`と`tools/skill_eval/validate_skill_evals.py`
- Production Quality Evaluation: `eval/`
- このDirectory: 手動CaseとReview補助

`cases.yaml`および`*_cases.yaml`の`prompt`を対象Agentへ与え、Primary Route / Skill、必要なSecondary Skill、`must_include` / `must_not` / `pass_condition`を記録します。

## Boundary checks

- SemanticなPrimary Route / Skillを一意に選べる
- Technology Keywordだけで隣接Routeへ誤発火しない
- Read-only依頼でMutationを始めない
- 指定Scope、Human Approval、Evidenceの境界を越えない
- 専門Skillの手順をOrchestrationで不要に複製しない

手動結果はPRまたはReview Noteに記録できます。Canonical EvalやRegression Gateの合格を代替しません。

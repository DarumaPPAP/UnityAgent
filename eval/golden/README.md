# UnityAgent Golden Behavior Evaluation

`eval/golden/`は、受け入れ済みのUnityAgent BehaviorとDecision BoundaryをRegression Assetとして固定するCanonical Evalです。HubのManifest ValidatorやBackend Compatibility Testの代替ではありません。

## 評価方針

- Golden Taskは受け入れ済みBehaviorと境界条件を保持します。
- 生成Sourceの完全一致を既定Graderにはせず、Deterministic OutcomeとInvariantを評価します。
- Positive / Negative Boundary Pairで過剰な禁止ルールへのOverfitを防ぎます。
- `unavailable`を`passed`として数えません。
- Context Manifest / Execution Graphは失敗原因を追跡するTraceです。

## Validate / Evaluate

```bash
python eval/golden/validate_required_knowledge.py
python eval/golden/validate_golden_tasks.py
python eval/golden/run_golden_evals.py --results Artifacts/GoldenEval/candidate-results.yaml
```

Candidate結果はRuntime実行側または比較Harnessが生成します。Eval自身はModelを呼び出しません。Project Regression Graphは次で生成します。

```bash
python eval/golden/project_regression_graph.py
```

Canonical Failure Attributionは`eval/attribution/`が所有します。`Artifacts/GoldenEval/`のSummary / Graphは派生物でありPolicyではありません。

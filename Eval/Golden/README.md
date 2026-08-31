# UnityAgent Golden Regression

Canonical Evalは、受け入れ済みのUnityAgent BehaviorをRegression Assetとして固定します。

## 基本原則

- Golden Taskは、受け入れ済みのBehaviorとDecision Boundaryを保持します。
- 生成Sourceの完全一致を既定のGraderにはしません。
- DeterministicなOutcomeとInvariantによる評価を優先します。
- Positive / NegativeのBoundary Pairによって、Policyを過剰に絶対禁止へ変換するOverfittingを防ぎます。
- `unavailable` を `passed` として数えません。
- Context Manifest / Execution Graphは、失敗原因を追跡するためのTraceとして保持します。

## Validation

```bash
python Eval/Golden/validate_required_knowledge.py
python Eval/Golden/validate_golden_tasks.py
```

## Candidate結果の評価

```bash
python Eval/Golden/run_golden_evals.py --results Artifacts/GoldenEval/candidate-results.yaml
```

Candidate ResultはRuntime実行側、またはModel比較Harnessが生成します。Eval自身はModelを呼び出しません。

## Project Regression Graph

```bash
python Eval/Golden/project_regression_graph.py
python Eval/Golden/project_regression_graph.py --results Artifacts/GoldenEval/candidate-results.yaml
```

## Failure Taxonomy

CanonicalなFailure Attributionは `Eval/Attribution/` で定義します。観測済みのAgent品質Failureと、Infrastructure / Evaluator / Evidence側のFailureを区別したまま扱います。

生成されたSummaryやGraphは `Artifacts/GoldenEval/` 配下に置きます。これらはCanonical Policyではありません。

# UnityAgent 3-Minute Architecture

UnityAgentを初見の人が短時間で理解するための **Human-facing Mental Model** です。

この文書はCanonical Architectureの代替Source of Truthではありません。Production Authorityは引き続き `Policy/`、`Orchestration/`、`Context/`、`Runtime/`、`Persistence/`、`Operations/`、`Eval/` にあります。

## 30秒版

UnityAgentは、Unity開発を次の3つとして扱います。

```text
THINK              ACT               VERIFY
判断・設計    ->    Unityを操作   ->   実測・評価
```

MyResourceCenterはUnityAgent内部のRuntimeではなく、必要な知識をReference Snapshotとして提供する独立したKnowledge Libraryです。

## 3分版: 7つだけ覚える

| Human Concept | 問い | Machine Mapping |
| --- | --- | --- |
| Rules | やっていい？ | `Policy/` |
| Planner | どう進める？ | `Orchestration/`、必要時だけGraph / Loop |
| Knowledge | 何を読む？ | `Context/`、`.agents/skills/`、MyResourceCenter Snapshot |
| Executor | 何を実行する？ | `Runtime/`、Provider / Harness |
| Evidence | 本当に起きた？ | `Runtime/EvidenceCapture/` |
| Memory | 何を残す？ | `Persistence/` |
| Quality | 悪化してない？ | `Eval/`、`Operations/` |

```text
Rules
  -> Planner
      -> Knowledge
          -> Executor
              -> Evidence
                  -> Memory
                  -> Quality
```

GraphはUnityAgent全体のRuntime Engineではありません。Plannerが複数判断や再計画を必要とするTaskでだけ使うStrategyです。

## 3つのシステム境界

```text
MyResourceCenter
  What do we know?
        |
        v
UnityAgent
  What should we do?
        |
        v
Unity Project
  What actually happened?
```

この分離により、Knowledgeの保管、Agentの判断、Projectの実測を同じ責務として混ぜません。

## 実Task例

依頼: `Shaderを最適化して`

```text
Rules
  変更範囲 / Platform / Evidence条件
        |
Planner
  Rendering / Performance Taskとして手順決定
        |
Knowledge
  Shader Skill / Project Fact / Reference Snapshot
        |
Executor
  Source / Variant / Profilerを観測・修正
        |
Evidence
  GPU時間 / Variant / Visual Fact
        |
Quality
  Regressionと改善結果を確認
```

## Architecture Explorer

`Tools/GraphObservatory/` のContext Explorerは、このMental Modelをアニメーション付きで表示します。

```powershell
python .\Tools\GraphObservatory\build.py --view context --bundle .\Artifacts\GraphObservatory\ContextExplorer
```

生成Bundleは次の4段階で情報を開示します。

```text
Guided Animation
    -> Human Concept
        -> Machine Subsystem
            -> Repository Source Path
```

加えて、実Task Demoと既存Context Packの検索・Relation探索を同じOffline HTMLから利用できます。

## 境界

- Human MapはCanonical Machine Architectureを書き換えない。
- Explorerはread-only / offlineであり、Save / Apply / Agent Controlを持たない。
- Missing Relationを推測で補完しない。
- Source PathはRepository内Pathだけを扱う。
- AccessibilityとしてKeyboard操作と`prefers-reduced-motion`を維持する。

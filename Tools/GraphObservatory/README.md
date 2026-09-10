# UnityAgent Architecture / Context Explorer

`Tools/GraphObservatory/` は、CanonicalなUnityAgent Contractから **読み取り専用のHuman Architecture / Context Projection** を生成する補助ツールです。

Production Authorityは `Policy/`、`Orchestration/`、`Context/`、`Runtime/`、`Persistence/`、`Operations/`、`Eval/` にあります。このToolが生成するGraphとHuman MapはDerived Viewであり、正本ではありません。

## 何を見るToolか

HTML Bundleは4段階で情報を開示します。

```text
3分Guided Animation
    -> 7つのHuman Concept
        -> Machine Subsystem
            -> Repository Source Path
```

Human Conceptは次の7つです。

```text
Rules -> Planner -> Knowledge -> Executor -> Evidence -> Memory / Quality
```

加えて次を同じOffline HTMLで確認できます。

- Shader最適化依頼を例にしたTask Demo
- MyResourceCenter / UnityAgent / Unity Projectの責務境界
- `Context/Packs/*.yaml` の検索
- Context Relation / Purpose / Decision / Forbidden / Provenance
- Source PathのCopyによるRepository drill-down

## 現在の入力

- Human Architecture: Canonical Repository Pathの存在を検証した`architecture_projection.py`
- Context View: `Context/Packs/*.yaml` の現行Metadata

single-repo cutoverで廃止された旧dot-ai treeをCurrent Sourceとして使用しません。

## BuildとValidation

```powershell
python .\Tools\GraphObservatory\build.py --view context --check
python .\Tools\GraphObservatory\build.py --view context --bundle .\Artifacts\GraphObservatory\ContextExplorer
```

BundleはStatic / Offlineです。生成後は `Artifacts/GraphObservatory/ContextExplorer/index.html` をブラウザで開きます。

## UX Contract

- 初見は`Overview`のGuided TourだけでMental Modelを理解できる
- `Task Demo`で実依頼とArchitectureの対応を理解できる
- `Explore`で初めてContext Packの詳細へ降りる
- Keyboard操作可能なButton / Input / Selectを使う
- `prefers-reduced-motion`では自動アニメーションを抑制する
- 外部CDN / HTTP fetch / Storage書き込みを使わない

## 境界

- ProjectionはSource Path / HashなどのProvenanceを保持する
- 不明なRelationを推測で埋めない
- Graph UIからCanonical Contractを変更しない
- Graph OutputをRoute、State、Evidence、Eval、Frozen BaselineのSource of Truthとして扱わない
- GraphはPlannerが必要時に利用するStrategyであり、UnityAgent全体のRuntime Engineとして表示しない
- 旧Builder / Projection Codeが残る場合もCompatibility AuthorityとしてProduction Bootstrapへ接続しない

Human-facing Mental Modelは [`docs/architecture/three-minute-architecture.md`](../../docs/architecture/three-minute-architecture.md)、Current Tool Contractは [`docs/graph-observatory-spec.md`](../../docs/graph-observatory-spec.md) を参照してください。

# Graph Observatory / Context Explorer

> Historical filename retained for link stability. This document describes the current post-Phase-8 supporting tool, not a separate Production authority.

## Goal

UnityAgentのcanonical contractからread-only graph / context projectionを生成し、Agent decisionのprovenanceやContext relationを人間が確認できるようにする。

Graph ObservatoryはProduction execution、Route selection、Policy編集、Regression判定のAuthorityではありません。

## Current authority inputs

```text
Policy/
Orchestration/
Context/
Runtime/
Persistence/
Eval/
        │
        ▼
read-only Graph / Context projection
        │
        ▼
Artifacts/GraphObservatory/**
        │
        ▼
Graph Observatory UI
```

現在のContext Explorerは主に `Context/Packs/*.yaml` のmetadataをread-only projectionします。

Legacy `.ai/*.yaml` はPhase 8で削除済みであり、current inputとして使用しません。

## Core views / direction

長期的なview候補:

- Architecture View
- Context Explorer
- Task / Route Explorer
- Execution Trace
- Regression Dashboard

実装済み範囲と将来候補を混同しません。現在の `Tools/GraphObservatory/build.py` が直接サポートするviewだけを実装済みとして扱います。

## Design principles

- Graph dataはcanonical sourceから生成するderived view。
- VisualizerはPolicy / Orchestration / Runtime / Eval contractを直接編集しない。
- Node / Edgeは可能な限りsource path / hash等のprovenanceを保持する。
- Missing relationを推測で補完しない。
- Empty projectionを「正常なcanonical graph」と誤認しない。
- Graph outputはdurable State / Evidence / Baselineの代替truthではない。

## Current build entry point

```powershell
python .\Tools\GraphObservatory\build.py --view context --check
```

Bundle生成:

```powershell
python .\Tools\GraphObservatory\build.py --view context --bundle .\Artifacts\GraphObservatory\ContextExplorer
```

## Non-goals

- second routing systemの作成
- legacy compatibility authorityの維持
- Graph UIからcanonical YAMLを直接変更
- GraphだけでRoot CauseやRegressionを確定
- Phase 9 Frozen BaselineやPhase 10 comparatorの代替

## Historical note

この機能はPhase 8期にGraph Observatoryとして開始されました。Phase 8 single-repo cutover後は、legacy `.ai` sourceではなくcurrent canonical pathsだけをprojection inputとして使用します。
